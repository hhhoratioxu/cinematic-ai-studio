"""Objective media QC; semantic/identity checks are explicitly probabilistic."""
from __future__ import annotations

import json
import math
import re
from fractions import Fraction
from pathlib import Path

from common import CinemaError, command, digest, media_tool, write_json


def probe(path: Path, settings=None):
    executable = media_tool("ffprobe", getattr(settings, "ffprobe", None))
    try:
        data = json.loads(command([executable, "-v", "error", "-show_format", "-show_streams",
                                   "-of", "json", str(path)]).stdout)
        data["duration"] = float(data.get("format", {}).get("duration", 0))
        data["video"] = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
        data["audio"] = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
        return data
    except (ValueError, KeyError) as e:
        raise CinemaError("Invalid FFprobe media report") from e


def inspect_video(path: Path, settings=None, duration=None, output=None, require_audio=False):
    try:
        data = probe(path, settings)
    except CinemaError:
        return {"file": str(path.resolve()), "sha256": digest(path) if path.is_file() else None,
                "technical_pass": False, "issues": ["probe_or_decode_error"],
                "semantic_quality": "unverified", "duration": 0, "fps": 0, "has_audio": False}
    issues = []
    video = data["video"]
    if not video or not math.isfinite(data["duration"]) or data["duration"] <= 0:
        issues.append("missing_video_or_duration")
    try:
        fps = float(Fraction(video.get("avg_frame_rate", "0/1"))) if video else 0
    except (ValueError, ZeroDivisionError):
        fps = 0
    if not fps:
        issues.append("invalid_frame_rate")
    if duration is not None and abs(data["duration"] - duration) > max(0.12, 2 / (fps or 24)):
        issues.append("duration_mismatch")
    if output and video:
        if (video["width"], video["height"]) != (output.width, output.height):
            issues.append("resolution_or_aspect_mismatch")
        if abs(fps - output.fps) > 0.01:
            issues.append("frame_rate_mismatch")
        if video.get("codec_name") != "h264":
            issues.append("video_codec_mismatch")
        if data["audio"] and data["audio"].get("codec_name") != "aac":
            issues.append("audio_codec_mismatch")
    if require_audio and not data["audio"]:
        issues.append("missing_audio_track")
    av_offset = None
    if video and data["audio"]:
        av_offset = abs(float(video.get("start_time", 0)) - float(data["audio"].get("start_time", 0)))
        if av_offset > 0.12:
            issues.append("stream_start_av_offset")
    executable = media_tool("ffmpeg", getattr(settings, "ffmpeg", None))
    try:
        command([executable, "-hide_banner", "-v", "error", "-xerror", "-i", str(path),
                 "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"], timeout=1800)
    except CinemaError:
        issues.append("decode_error")
    try:
        result = command([executable, "-hide_banner", "-nostdin", "-i", str(path), "-an", "-vf",
                          "blackdetect=d=0.25:pix_th=0.10:pic_th=0.98,freezedetect=n=-50dB:d=0.75",
                          "-f", "null", "-"], timeout=1800)
        analysis = result.stderr
    except CinemaError:
        analysis = ""
        issues.append("motion_analysis_error")
    blacks = [float(v) for v in re.findall(r"black_duration:([0-9.]+)", analysis)]
    freeze_starts = re.findall(r"freeze_start:\s*([0-9.]+)", analysis)
    if blacks:
        issues.append("black_frames")
    if freeze_starts:
        issues.append("frozen_frames")
    report = {"file": str(path.resolve()), "sha256": digest(path), "duration": data["duration"], "fps": fps,
              "width": video.get("width") if video else None, "height": video.get("height") if video else None,
              "has_audio": bool(data["audio"]), "av_stream_start_offset": av_offset,
              "black_intervals_seconds": blacks, "freeze_starts": [float(v) for v in freeze_starts],
              "issues": issues, "technical_pass": not issues,
              "semantic_quality": "unverified",
              "limitations": ["Motion detection cannot prove acting, anatomy, identity or lip-sync accuracy.",
                              "AV stream timestamps do not measure mouth-to-speech alignment."]}
    return report


def require_pass(report, shot_id):
    if not report["technical_pass"]:
        raise CinemaError(f"Shot {shot_id} QC failed: {', '.join(report['issues'])}")


def frame_samples(path: Path, directory: Path, settings, duration: float):
    directory.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, t in enumerate((0.2, duration / 2, max(0.2, duration - 0.25))):
        output = directory / f"frame_{i}.jpg"
        command([media_tool("ffmpeg", settings.ffmpeg), "-v", "error", "-y", "-ss", str(t),
                 "-i", str(path), "-frames:v", "1", "-vf", "scale=640:-2", str(output)])
        frames.append(output)
    return frames


def vision_check(path, shot, characters, settings, ledger, directory, provider=None):
    from image_engine import rate
    from providers.base import SyncJobs
    from providers.openai_api import OpenAI
    frames = frame_samples(path, directory, settings, shot.duration)
    refs = [Path(c.references["front"]) for c in characters]
    prompt = ("Return JSON with fields severe_issue (boolean), observations (array of strings), "
              "identity_concern (boolean), action_concern (boolean), uncertainty (string). "
              "First images are character references in this order: " + ",".join(c.name for c in characters) +
              ". Last three images are chronological samples of the generated shot. "
              f"Intended action: {shot.action} {shot.temporal_motion}. "
              "Compare identity, wardrobe, anatomy and intended action. Acknowledge sparse samples cannot "
              "prove continuous motion or audio synchronization; flag uncertainty rather than invent evidence.")
    spec = {"model": settings.vision_model, "prompt": prompt, "images": [digest(p) for p in refs + frames]}
    api = provider or OpenAI()
    output = directory / "vision.json"
    SyncJobs(ledger).run("openai", "vision", spec, output, rate(settings, "openai:vision"),
                         lambda p: api.response_json(prompt, p, settings.vision_model, refs + frames, 1200))
    result = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(result.get("severe_issue"), bool):
        raise CinemaError("Vision QC returned an invalid assessment; manual review required")
    result["evidence"] = "probabilistic_sparse_frame_review"
    write_json(directory / "vision_assessment.json", result)
    return result
