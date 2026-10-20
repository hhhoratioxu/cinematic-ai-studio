"""Real moving-shot production with bounded retries and configured-provider fallback."""
from __future__ import annotations

from pathlib import Path

from common import CinemaError, TaskFailed, digest, write_json
from image_engine import rate
from providers.base import AsyncJobs
from providers.kling import Kling
from providers.runway import Runway
from quality_control import inspect_video, vision_check
from storyboard_engine import video_prompt


def ratio(width, height, provider):
    import math
    gcd = math.gcd(width, height)
    aspect = f"{width // gcd}:{height // gcd}"
    if provider == "kling":
        if aspect not in ("9:16", "16:9", "1:1"):
            raise CinemaError("Kling adapter supports 9:16, 16:9, 1:1")
        return aspect
    mapping = {"9:16": "720:1280", "16:9": "1280:720", "1:1": "960:960",
               "3:4": "832:1104", "4:3": "1104:832", "33:14": "1584:672"}
    if aspect not in mapping:
        raise CinemaError(f"No verified native Runway ratio for {aspect}")
    return mapping[aspect]


def make_spec(plan, shot, characters, provider_config, first_frame=None):
    frames = {"first_frame": str(first_frame or shot.first_frame) if first_frame or shot.first_frame else None,
              "last_frame": shot.last_frame}
    hashes = {name: digest(Path(value)) for name, value in frames.items() if value and Path(value).is_file()}
    return {"model": provider_config.model, "mode": provider_config.mode,
            "prompt": video_prompt(plan, shot, characters), "duration": shot.duration,
            "ratio": ratio(plan.output.width, plan.output.height, "runway") if provider_config.name == "runway"
            else "unused", "aspect_ratio": ratio(plan.output.width, plan.output.height, "kling")
            if provider_config.name == "kling" else "unused", **frames, "frame_hashes": hashes,
            "elements": shot.elements, "native_audio": shot.native_audio,
            "character_bible": [c.model_dump() for c in characters]}


def provider_ready(name):
    import os
    if name == "runway":
        return bool(os.environ.get("RUNWAYML_API_SECRET"))
    return bool(os.environ.get("KLING_API_KEY") or
                (os.environ.get("KLING_ACCESS_KEY") and os.environ.get("KLING_SECRET_KEY")))


def validate_video_plan(plan, settings, require_keys=True):
    """Check every shot before buying even its first character image."""
    reports = []
    for shot in plan.shots:
        characters = [c for c in plan.characters if c.id in shot.characters]
        problems, usable = [], []
        for config in settings.video:
            try:
                if require_keys and not provider_ready(config.name):
                    raise CinemaError("API credentials are not configured")
                spec = make_spec(plan, shot, characters, config,
                                 "generated_scene" if shot.generation == "image_to_video" else None)
                # No HTTP client or authentication is constructed for offline capability validation.
                provider = object.__new__(Runway if config.name == "runway" else Kling)
                provider.validate(spec)
                if require_keys:
                    rate(settings, f"{config.name}:video:{config.model}", shot.duration)
                usable.append(config.name)
            except CinemaError as e:
                problems.append(f"{config.name}: {e}")
        if not usable:
            raise CinemaError(f"Shot {shot.id} has no usable configured provider: {'; '.join(problems)}")
        onscreen = [d for d in shot.dialogue if d.delivery == "onscreen"]
        if settings.lipsync == "sync" and shot.native_audio == "replace" and onscreen:
            if len(shot.characters) != 1 or len({d.character for d in onscreen}) != 1:
                raise CinemaError(f"{shot.id}: Sync adapter requires a single visible speaker; use reverse shots, "
                                  "native audio, or explicitly configure lipsync=off with manual review")
        reports.append({"shot": shot.id, "usable": usable, "skipped": problems})
    return reports


class VideoEngine:
    def __init__(self, settings, ledger, jobs=None, factories=None):
        self.settings = settings
        self.ledger = ledger
        self.jobs = jobs or AsyncJobs(ledger, settings.poll_seconds, settings.task_timeout_seconds)
        self.factories = factories or {"runway": Runway, "kling": Kling}

    def generate(self, plan, shot, characters, first_frame, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        failures = []
        for config in self.settings.video:
            if not provider_ready(config.name) and self.factories.get(config.name) in (Runway, Kling):
                failures.append(f"{config.name}: no credentials")
                continue
            provider = self.factories[config.name]()
            spec = make_spec(plan, shot, characters, config, first_frame)
            try:
                provider.validate(spec)
            except CinemaError as e:
                failures.append(f"{config.name}: {e}")
                continue
            for attempt in range(self.settings.max_attempts):
                attempt_spec = dict(spec)
                if attempt:
                    attempt_spec["prompt"] = spec["prompt"].replace(
                        "no freeze", "continuous body motion, no freeze")
                provider.validate(attempt_spec)
                output = directory / f"{config.name}_attempt_{attempt + 1}.mp4"
                try:
                    output, key = self.jobs.run(provider, attempt_spec, output,
                                               rate(self.settings, f"{config.name}:video:{config.model}",
                                                    shot.duration), attempt=attempt)
                except TaskFailed as e:
                    failures.append(str(e))
                    write_json(directory / "failures.json", failures)
                    continue
                # Transport/download failures and uncertain submissions intentionally propagate.
                qc = inspect_video(output, self.settings, duration=shot.duration,
                                   require_audio=shot.native_audio == "preserve")
                if self.settings.vision_qc and qc["technical_pass"]:
                    qc["vision"] = vision_check(output, shot, characters, self.settings, self.ledger,
                                                 directory / f"vision_{config.name}_{attempt}")
                    if qc["vision"]["severe_issue"]:
                        qc["issues"].append("vision_model_flagged_severe_issue")
                        qc["technical_pass"] = False
                write_json(directory / f"qc_{config.name}_{attempt + 1}.json", qc)
                if qc["technical_pass"]:
                    row = self.ledger.get(key)
                    return output, {"shot_id": shot.id, "provider": config.name, "model": config.model,
                                    "task_id": row["task_id"], "task_key": key, "sha256": digest(output),
                                    "qc": qc, "evidence": getattr(provider, "evidence", "real_api_video"),
                                    "failures_before_acceptance": failures}
                self.ledger.update(key, state="rejected", error=",".join(qc["issues"]))
                failures.append(f"{shot.id} {config.name} attempt {attempt + 1}: {qc['issues']}")
                write_json(directory / "failures.json", failures)
        raise CinemaError(f"Shot {shot.id} exhausted bounded attempts: {'; '.join(failures)}")


def decoded_signature(path, settings):
    from common import command, content_key, media_tool
    output = command([media_tool("ffmpeg", settings.ffmpeg), "-v", "error", "-i", str(path), "-an",
                      "-vf", "fps=2,scale=64:64,format=gray", "-f", "framemd5", "-"]).stdout
    hashes = [line.split(",")[-1].strip() for line in output.splitlines() if line and not line.startswith("#")]
    return content_key(hashes)
