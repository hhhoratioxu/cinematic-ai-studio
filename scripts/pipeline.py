"""A complete episode pipeline; production never falls back to synthetic footage."""
from __future__ import annotations

import concurrent.futures
import threading
from pathlib import Path

from audio_engine import AudioEngine, original_score, subtitles
from character_engine import prepare_characters
from common import CinemaError, TaskFailed, content_key, digest, write_json
from editing_engine import export_episode, normalize_shot
from image_engine import ImageEngine, rate
from models import Plan, Settings
from providers.base import AsyncJobs
from providers.sync_lipsync import SyncLipsync
from quality_control import inspect_video, require_pass
from state import Ledger
from video_engine import VideoEngine, decoded_signature, validate_video_plan


def estimate(plan: Plan, settings: Settings):
    items = []
    missing = set()
    def add(label, unit, units):
        value = settings.ceilings_usd.get(unit)
        if value is None:
            missing.add(unit)
        items.append({"item": label, "rate_key": unit, "units": units,
                      "ceiling_usd": None if value is None else round(value * units, 6)})
    for c in plan.characters:
        for view in ("front", "side", "full_body"):
            if view not in c.references:
                add(f"character:{c.id}:{view}", "openai:image", 1)
    for shot in plan.shots:
        if shot.generation == "image_to_video" and not shot.first_frame:
            add(f"scene:{shot.id}", "openai:image", 1)
        for config in settings.video:
            add(f"video:{shot.id}:{config.name}", f"{config.name}:video:{config.model}",
                shot.duration * settings.max_attempts)
        if settings.vision_qc:
            add(f"vision:{shot.id}", "openai:vision", settings.max_attempts * len(settings.video))
        if shot.native_audio == "replace":
            for i, _ in enumerate(shot.dialogue):
                add(f"dialogue:{shot.id}:{i}", "openai:tts", 1)
            if settings.lipsync == "sync" and any(d.delivery == "onscreen" for d in shot.dialogue):
                add(f"lipsync:{shot.id}", "sync:lipsync", shot.duration * settings.max_attempts)
        for sound in shot.sounds:
            if not sound.file:
                add(f"sound:{shot.id}:{sound.id}", "runway:sfx", sound.duration)
    total = None if missing else round(sum(item["ceiling_usd"] for item in items), 6)
    return {"target_seconds": plan.target_seconds, "shot_count": len(plan.shots),
            "all_attempts_and_configured_fallbacks_ceiling_usd": total, "missing_rates": sorted(missing),
            "items": items, "actual_billed_usd": None,
            "note": "Upper-bound reservations from your reviewed rates; no vendor price is inferred. "
                    "Includes bounded video/lipsync retries and fallback providers, excludes optional story "
                    "planning (separate reservation). Provider invoices determine actual charges."}


def check_environment(plan, settings):
    import os
    validate_video_plan(plan, settings)
    needs_openai = any(not all(k in c.references for k in ("front", "side", "full_body"))
                       for c in plan.characters)
    needs_openai |= any(s.generation == "image_to_video" and not s.first_frame for s in plan.shots)
    needs_openai |= settings.vision_qc or any(s.dialogue and s.native_audio == "replace" for s in plan.shots)
    if needs_openai and not os.environ.get("OPENAI_API_KEY"):
        raise CinemaError("OPENAI_API_KEY required for planned images, speech or vision checks")
    if any(not sound.file for s in plan.shots for sound in s.sounds) and not os.environ.get("RUNWAYML_API_SECRET"):
        raise CinemaError("RUNWAYML_API_SECRET required for generated sound effects; alternatively import licensed files")
    if settings.lipsync == "sync" and any(s.native_audio == "replace" and
            any(d.delivery == "onscreen" for d in s.dialogue) for s in plan.shots):
        if not os.environ.get("SYNC_API_KEY"):
            raise CinemaError("SYNC_API_KEY required for on-screen dubbed speech; explicit lipsync=off permits "
                              "unsynchronized dubbing with manual-review status")
    report = estimate(plan, settings)
    if report["missing_rates"]:
        raise CinemaError("Configure cost ceilings: " + ", ".join(report["missing_rates"]))
    from common import media_tool
    media_tool("ffmpeg", settings.ffmpeg)
    media_tool("ffprobe", settings.ffprobe)
    return report


def render_episode(plan: Plan, settings: Settings, directory: Path, budget: float, authorized: bool,
                   ledger: Ledger | None = None, event=None):
    from fonts import select_font
    needs_subtitles = plan.output.burn_subtitles and any(s.dialogue for s in plan.shots)
    plan = plan.model_copy(update={"output": select_font(plan.output, needed=needs_subtitles)})
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    edit = directory / "edit"
    edit.mkdir(exist_ok=True)
    subtitles(plan, edit)  # Reject unsafe line lengths before paying for any generated assets.
    report = check_environment(plan, settings)
    write_json(directory / "estimate.json", report)
    own_ledger = ledger is None
    ledger = ledger or Ledger(directory / "tasks.sqlite3", budget, authorized)
    snapshots = {"plan": plan.model_dump(), "settings": settings.model_dump()}
    external_files = [Path(v) for c in plan.characters for v in c.references.values()]
    external_files += [Path(v) for s in plan.shots for v in (s.first_frame, s.last_frame) if v]
    external_files += [Path(sound.file) for s in plan.shots for sound in s.sounds if sound.file]
    external_files += [Path(plan.music_file)] if plan.music_file else []
    fingerprint = {"inputs": snapshots, "files": {str(p): digest(p) for p in external_files}}
    ledger.bind("production_inputs", content_key(fingerprint))
    write_json(directory / "run.json", {**snapshots, "budget_usd": budget, "test_only": False})
    notify = event or (lambda value: None)
    write_json(directory / "manifest.json", {"status": "in_progress", "test_only": False, "shots": []})
    try:
        characters = prepare_characters(plan, ImageEngine(settings, ledger), directory / "characters", directory)
        working = plan.model_copy(update={"characters": characters})
        write_json(directory / "shot_plan.json", working.model_dump())
        results = {}
        cancellation = threading.Event()
        def process(shot):
            if cancellation.is_set():
                raise CinemaError("Stopped after another shot failed; resume will reuse accepted shots")
            notify({"stage": "shot", "shot": shot.id})
            root = directory / "shots" / shot.id
            root.mkdir(parents=True, exist_ok=True)
            cast = [c for c in characters if c.id in shot.characters]
            audio = AudioEngine(settings, ledger)
            spoken, timing = audio.dialogue(shot, characters, root / "audio")
            first = Path(shot.first_frame) if shot.first_frame else None
            if shot.generation == "image_to_video" and not first:
                first = ImageEngine(settings, ledger).scene(working, shot, cast, directory / "scenes")
            video, provenance = VideoEngine(settings, ledger).generate(working, shot, cast, first, root)
            provenance["generated_file"] = str(video)
            if settings.lipsync == "sync" and shot.native_audio == "replace" and any(
                    d.delivery == "onscreen" for d in shot.dialogue):
                sync_spec = {"model": settings.lipsync_model, "video": str(video), "audio": str(spoken),
                             "video_sha256": digest(video), "audio_sha256": digest(spoken)}
                jobs = AsyncJobs(ledger, settings.poll_seconds, settings.task_timeout_seconds)
                for attempt in range(settings.max_attempts):
                    try:
                        synced, sync_key = jobs.run(SyncLipsync(), sync_spec,
                            root / f"lipsync_{attempt + 1}.mp4", rate(settings, "sync:lipsync", shot.duration),
                            kind="lipsync", attempt=attempt)
                    except TaskFailed:
                        if attempt + 1 == settings.max_attempts:
                            raise
                        continue
                    qc = inspect_video(synced, settings, duration=shot.duration)
                    write_json(root / f"qc_lipsync_{attempt + 1}.json", qc)
                    if qc["technical_pass"]:
                        video = synced
                        provenance["lipsync"] = {"task_key": sync_key,
                                                  "task_id": ledger.get(sync_key)["task_id"],
                                                  "accuracy": "requires audiovisual review"}
                        break
                    ledger.update(sync_key, state="rejected", error=",".join(qc["issues"]))
                else:
                    raise CinemaError(f"{shot.id}: lip-sync QC exhausted bounded attempts")
            tracks = audio.sound_tracks(shot, root / "audio")
            if shot.native_audio == "preserve":
                tracks.insert(0, {"file": video, "start": 0, "gain_db": 0})
            else:
                tracks.insert(0, {"file": spoken, "start": 0, "gain_db": 0})
            mixed = audio.mix(shot.duration, tracks, root / "audio" / "mixed.wav")
            normalized = directory / "normalized" / f"{shot.id}.mkv"
            provenance["postprocessing"] = normalize_shot(video, mixed, normalized, shot, plan.output, settings)
            provenance["normalized_sha256"] = digest(normalized)
            provenance["decoded_signature"] = decoded_signature(video, settings)
            provenance["source_file"] = str(video)
            provenance["source_sha256"] = digest(video)
            write_json(root / "accepted.json", provenance)
            notify({"stage": "accepted", "shot": shot.id})
            return normalized, provenance, timing
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.max_concurrency) as pool:
            futures = {pool.submit(process, shot): shot.id for shot in working.shots}
            try:
                for future in concurrent.futures.as_completed(futures):
                    results[futures[future]] = future.result()
            except BaseException:
                cancellation.set()
                for future in futures:
                    future.cancel()
                raise
        ordered = [results[shot.id] for shot in working.shots]
        if any(entry[1]["evidence"] != "real_api_video" for entry in ordered):
            raise CinemaError("Synthetic/mock footage cannot enter a production episode")
        signatures = [entry[1]["decoded_signature"] for entry in ordered]
        if len(set(signatures)) != len(signatures):
            raise CinemaError("Duplicate decoded shot content detected; no completed episode exported")
        edit = directory / "edit"
        edit.mkdir(exist_ok=True)
        srt, ass = subtitles(working, edit, {s.id: results[s.id][2] for s in working.shots})
        music = Path(plan.music_file) if plan.music_file else None
        if not music and plan.original_score:
            music = original_score(directory / "audio" / "original_ambient_score.wav", plan.target_seconds)
        final = export_episode([entry[0] for entry in ordered], working, edit, settings, music)
        qc = inspect_video(final, settings, plan.target_seconds, plan.output, require_audio=True)
        qc["shot_coverage"] = {"expected": len(working.shots), "accepted": len(ordered),
                                "missing": [], "duplicate_decoded_shots": False}
        write_json(directory / "qc_report.json", qc)
        require_pass(qc, "final_episode")
        manifest = {"version": 1, "status": "rendered_requires_editorial_review", "test_only": False,
                    "title": plan.title, "episode": plan.episode, "mode": plan.mode,
                    "target_seconds": plan.target_seconds, "output": str(final), "sha256": digest(final),
                    "shots": [entry[1] for entry in ordered], "technical_qc": qc,
                    "subtitles": str(srt), "music": {"file": str(music) if music else None,
                        "rights": plan.music_license if plan.music_file else "original procedural ambient score"},
                    "disclosure": "AI-generated footage and synthetic voices. Technical QC does not certify "
                                  "identity, acting, anatomy, lip-sync, subtitle glyph bounds or cinematic quality.",
                    "cost": ledger.summary()}
        write_json(directory / "manifest.json", manifest)
        return manifest
    except BaseException as e:
        write_json(directory / "manifest.json", {"status": "incomplete", "test_only": False,
                   "error": str(e), "cost": ledger.summary(),
                   "accepted_shots": [p.parent.name for p in (directory / "shots").glob("*/accepted.json")]})
        raise
    finally:
        write_json(directory / "cost_report.json", ledger.summary())
        if own_ledger:
            ledger.close()
