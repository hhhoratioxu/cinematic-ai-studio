from __future__ import annotations

import subprocess

import cv2
import numpy as np
import pytest

from common import media_tool
from motion_engine import analyze_motion
from quality_control import inspect_video


@pytest.fixture(scope="module")
def motion_clips(tmp_path_factory):
    folder = tmp_path_factory.mktemp("motion-analysis")
    rng = np.random.default_rng(817)
    base = cv2.GaussianBlur(rng.integers(25, 230, (320, 480), dtype=np.uint8), (3, 3), 0)
    paths = {}
    for kind in ("still", "pan", "articulated", "flash", "loop"):
        frames = []
        for index in range(72):
            tick = index % 24 if kind == "loop" else index
            x = 40 + tick if kind not in ("still", "flash") else 40
            frame = base[32:288, x:x + 240].copy()
            if kind == "articulated":
                cv2.circle(frame, (90 + int(40 * np.sin(index / 8)), 120), 28, 245, -1)
                cv2.line(frame, (120, 220), (90 + int(40 * np.sin(index / 8)), 120), 15, 10)
            if kind == "flash" and index in (25, 26, 50):
                frame[:] = 245
            frames.append(frame)
        output = folder / f"{kind}.mp4"
        result = subprocess.run([media_tool("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo",
            "-pixel_format", "gray", "-video_size", "240x256", "-framerate", "24", "-i", "-",
            "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(output)],
            input=np.asarray(frames).tobytes(), capture_output=True)
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        paths[kind] = output
    return paths


def test_motion_detects_camera_only_planar_pan(settings, motion_clips):
    report = analyze_motion(motion_clips["pan"], settings)
    assert "suspected_planar_pan_or_zoom" in report["flags"]
    assert report["planar_pair_fraction"] > 0.6
    assert report["status"] == "needs_review"
    assert report["coverage_seconds"] == 3
    assert len(report["temporal_thirds"]) == 3


def test_motion_compensates_camera_and_measures_independent_region(settings, motion_clips, shot):
    from models import SubjectRegion
    shot.subject_regions = [SubjectRegion(character="actor_a", box=(0.15, 0.15, 0.7, 0.8), source="user")]
    pan = analyze_motion(motion_clips["pan"], settings, shot)
    dynamic = analyze_motion(motion_clips["articulated"], settings, shot)
    assert dynamic["camera_compensated_change"] > pan["camera_compensated_change"] + 0.5
    assert dynamic["subject_region_change"][0] > pan["subject_region_change"][0]
    assert "not segmentation" in dynamic["subject_region_basis"]


def test_deliberate_hold_is_reviewed_instead_of_technical_freeze_rejection(settings, motion_clips, shot):
    shot.motion_policy = "hold"
    report = inspect_video(motion_clips["still"], settings, duration=3, shot=shot)
    assert report["technical_pass"]
    assert report["motion"]["status"] == "needs_review"
    assert "low_or_frozen_motion" in report["motion"]["flags"]


def test_flash_and_repeated_sequences_are_visible_evidence(settings, motion_clips):
    report = analyze_motion(motion_clips["flash"], settings)
    assert report["flash_times"] and "possible_flash_or_flicker" in report["flags"]
    repeated = analyze_motion(motion_clips["loop"], settings)
    assert repeated["repeated_sample_fraction"] > 0.2
    assert "repeated_sampled_content" in repeated["flags"]


def test_missing_motion_backend_is_not_silently_accepted(settings, media_factory, monkeypatch):
    import motion_engine
    def fail(*args):
        raise ImportError("test missing backend")
    monkeypatch.setattr(motion_engine, "analyze_motion", fail)
    report = inspect_video(media_factory(), settings)
    assert report["motion"]["status"] == "needs_review"
    assert "analysis_unavailable" in report["motion"]["flags"]
