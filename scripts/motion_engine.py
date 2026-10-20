"""Sampled motion evidence using optical flow and camera-compensated image residuals.

These heuristics triage footage. They do not establish character identity, acting,
true 3D geometry, or the physical origin of a video.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from common import CinemaError, media_tool


def analyze_motion(path: Path, settings=None, shot=None, duration=None):
    import cv2
    import numpy as np
    from quality_control import probe
    info = probe(path, settings)
    video = info["video"]
    if not video:
        raise CinemaError("Motion analysis requires a video stream")
    seconds = float(duration or info["duration"])
    requested = getattr(settings, "motion_sample_fps", 6)
    sample_fps = min(requested, 1200 / max(seconds, 0.1))
    scale = min(1, 320 / max(video["width"], video["height"]))
    width = max(2, int(video["width"] * scale) // 2 * 2)
    height = max(2, int(video["height"] * scale) // 2 * 2)
    args = [media_tool("ffmpeg", getattr(settings, "ffmpeg", None)), "-v", "error", "-i", str(path),
            "-an", "-vf", f"fps={sample_fps:.8f},scale={width}:{height},format=gray",
            "-frames:v", "1200", "-f", "rawvideo", "-"]
    result = subprocess.run(args, capture_output=True, timeout=1800)
    if result.returncode:
        raise CinemaError("FFmpeg motion sampling failed")
    size = width * height
    frames = np.frombuffer(result.stdout[:len(result.stdout) // size * size], np.uint8).reshape(-1, height, width)
    if len(frames) < 2:
        return {"status": "needs_review", "flags": ["insufficient_motion_samples"], "samples": len(frames)}
    raw, residuals, camera, inliers, subject, brightness = [], [], [], [], [], []
    regions = [r.model_dump() for r in shot.subject_regions] if shot and shot.subject_regions else []
    region_basis = "explicit normalized regions (planned/user/detector; not segmentation)" if regions else "center proxy; subject identity/position unknown"
    if not regions:
        regions = [{"box": (0.2, 0.12, 0.6, 0.76), "character": None, "source": "center_proxy"}]
    fingerprints = []
    for frame in frames:
        fingerprints.append(hashlib.sha256((cv2.resize(frame, (32, 32)) // 8).tobytes()).hexdigest())
    for previous, current in zip(frames[:-1], frames[1:]):
        raw.append(float(np.mean(cv2.absdiff(previous, current))))
        brightness.append(float(np.mean(current)) - float(np.mean(previous)))
        # Track textured features and fit a camera-like similarity transform.
        points = cv2.goodFeaturesToTrack(previous, 240, 0.01, 5)
        matrix, mask, moved = None, None, 0.0
        if points is not None and len(points) >= 8:
            following, status, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None)
            valid = status.reshape(-1).astype(bool) if status is not None else []
            if following is not None and np.count_nonzero(valid) >= 8:
                a, b = points[valid].reshape(-1, 2), following[valid].reshape(-1, 2)
                matrix, mask = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC,
                                                          ransacReprojThreshold=1.25)
                if matrix is not None:
                    corners = np.float32([[0, 0], [width, 0], [0, height], [width, height]])
                    transformed = cv2.transform(corners[None], matrix)[0]
                    moved = float(np.mean(np.linalg.norm(transformed - corners, axis=1)))
        if matrix is None:
            matrix = np.float64([[1, 0, 0], [0, 1, 0]])
        aligned = cv2.warpAffine(previous, matrix, (width, height))
        valid_pixels = cv2.warpAffine(np.full_like(previous, 255), matrix, (width, height)) > 254
        # Exclude interpolation/border artifacts before measuring independent motion.
        valid_pixels = cv2.erode(valid_pixels.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        delta = cv2.absdiff(aligned, current)
        residuals.append(float(np.mean(delta[valid_pixels])) if valid_pixels.any() else raw[-1])
        camera.append(moved)
        inliers.append(float(np.mean(mask)) if mask is not None else 0)
        values = []
        for region in regions:
            x, y, w, h = region["box"]
            roi = delta[int(y * height):int((y + h) * height), int(x * width):int((x + w) * width)]
            valid_roi = valid_pixels[int(y * height):int((y + h) * height), int(x * width):int((x + w) * width)]
            values.append(float(np.mean(roi[valid_roi])) if valid_roi.any() else 0)
        subject.append(values)
    raw, residuals, camera, inliers, subject = map(np.asarray, (raw, residuals, camera, inliers, subject))
    static = raw < 0.15
    planar = (camera > 0.25) & (inliers > 0.91) & (residuals < 1.8) & (raw > 0.8)
    cuts = np.flatnonzero((raw > 28) & (residuals > 18)).tolist()
    flash = [i for i in range(len(brightness) - 1) if abs(brightness[i]) > 18 and
             abs(brightness[i + 1]) > 18 and brightness[i] * brightness[i + 1] < 0]
    seen, distant_repeats = {}, []
    for i, value in enumerate(fingerprints):
        if value in seen and i - seen[value] > sample_fps * 0.75:
            distant_repeats.append(i)
        seen.setdefault(value, i)
    policy = shot.motion_policy if shot else "required"
    flags = []
    if np.mean(static) > 0.65:
        flags.append("low_or_frozen_motion")
    if np.mean(planar) > 0.6:
        flags.append("suspected_planar_pan_or_zoom")
    if len(distant_repeats) / len(frames) > 0.25:
        flags.append("repeated_sampled_content")
    if cuts:
        flags.append("abrupt_visual_changes")
    if flash:
        flags.append("possible_flash_or_flicker")
    if float(np.mean(subject)) < 0.5:
        flags.append("subject_motion_not_established")
    # Restrained acting and designed holds are legitimate, but demand human judgement.
    needs_review = bool(flags) or policy in ("hold", "subtle")
    bins = np.array_split(np.arange(len(raw)), 3)
    return {"status": "needs_review" if needs_review else "motion_observed_semantics_unverified",
            "flags": flags, "motion_policy": policy, "samples": len(frames),
            "sample_fps": round(sample_fps, 6), "coverage_seconds": seconds,
            "sampling": "Uniform samples across the entire clip; intervening frames are not all inspected",
            "static_pair_fraction": round(float(np.mean(static)), 4),
            "planar_pair_fraction": round(float(np.mean(planar)), 4),
            "mean_pixel_change": round(float(np.mean(raw)), 4),
            "camera_compensated_change": round(float(np.mean(residuals)), 4),
            "camera_displacement_pixels": round(float(np.mean(camera)), 4),
            "subject_region_change": [round(float(v), 4) for v in np.mean(subject, axis=0)],
            "subject_region_basis": region_basis,
            "temporal_thirds": [{"mean_change": round(float(np.mean(raw[b])), 4),
                                 "independent_change": round(float(np.mean(residuals[b])), 4)} for b in bins if len(b)],
            "abrupt_change_times": [round((i + 1) / sample_fps, 3) for i in cuts],
            "flash_times": [round((i + 1) / sample_fps, 3) for i in flash],
            "repeated_sample_fraction": round(len(distant_repeats) / len(frames), 4),
            "limitations": ["A camera-compensated residual cannot prove articulated character motion.",
                            "Parallax, changing light, animation and smooth real camera motion can confuse heuristics.",
                            "A hold/subtle performance or uncertain subject region requires editorial review."]}
