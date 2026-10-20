"""FFmpeg postproduction of already generated moving footage; no image animation."""
from __future__ import annotations

import shutil
from pathlib import Path

from common import CinemaError, atomic_bytes, command, media_tool
from quality_control import probe


def normalize_shot(source: Path, audio: Path, output: Path, shot, spec, settings):
    info = probe(source, settings)
    if not info["video"] or info["duration"] + 0.08 < shot.duration:
        raise CinemaError(f"{shot.id}: source footage shorter than the shot; never extend or loop video")
    output.parent.mkdir(parents=True, exist_ok=True)
    vf = (f"fps={spec.fps},scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease:"
          f"flags=lanczos,pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
    grades = {"neutral": "null", "warm": "colorbalance=rs=0.025:bs=-0.025:rh=0.015:bh=-0.015",
              "cool": "colorbalance=rs=-0.02:bs=0.025:rh=-0.01:bh=0.015"}
    vf += "," + grades[spec.grade]
    command([media_tool("ffmpeg", settings.ffmpeg), "-v", "error", "-y", "-i", str(source),
             "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
             "-af", f"apad,atrim=duration={shot.duration},aresample=48000", "-t", str(shot.duration),
             "-c:v", "libx264", "-crf", str(spec.crf), "-preset", "medium", "-pix_fmt", "yuv420p",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
             "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(output)])
    return {"source_width": info["video"]["width"], "source_height": info["video"]["height"],
            "output_width": spec.width, "output_height": spec.height,
            "grade": spec.grade,
            "upscaled_in_post": info["video"]["width"] < spec.width or info["video"]["height"] < spec.height,
            "scaling_method": "Lanczos resampling; not native model resolution"}


def export_episode(clips: list[Path], plan, directory: Path, settings, music: Path | None = None, test_only=False):
    directory.mkdir(parents=True, exist_ok=True)
    # Generated filenames contain no quotes; concat is never built from story/dialogue strings.
    for i, clip in enumerate(clips):
        target = directory / f"clip_{i:04d}.mkv"
        if clip.resolve() != target.resolve():
            shutil.copy2(clip, target)
    atomic_bytes(directory / "concat.txt", "".join(f"file 'clip_{i:04d}.mkv'\n"
                                                    for i in range(len(clips))).encode())
    if plan.output.font_file:
        fonts = directory / "fonts"
        fonts.mkdir(exist_ok=True)
        # Copy bytes only: macOS system fonts carry protected flags that must not
        # be propagated to a normal project's temporary font copy.
        shutil.copyfile(plan.output.font_file, fonts / Path(plan.output.font_file).name)
    args = [media_tool("ffmpeg", settings.ffmpeg), "-hide_banner", "-v", "error", "-y", "-f", "concat",
            "-safe", "1", "-i", "concat.txt"]
    if music:
        args += ["-stream_loop", "-1", "-i", str(music.resolve())]
        # Sidechain ducking gives dialogue priority; the original/native audio is included exactly once.
        args += ["-filter_complex", "[0:a]asplit=2[voice][key];[1:a]volume=0.13[bed];"
                 "[bed][key]sidechaincompress=threshold=0.025:ratio=10:attack=15:release=350[ducked];"
                 "[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
                 "-map", "0:v:0", "-map", "[a]"]
    else:
        args += ["-map", "0:v:0", "-map", "0:a:0"]
    if plan.output.burn_subtitles and any(s.dialogue for s in plan.shots):
        args += ["-vf", "ass=subtitles.ass:fontsdir=fonts", "-c:v", "libx264", "-crf", str(plan.output.crf),
                 "-preset", "medium"]
    else:
        args += ["-c:v", "copy"]
    name = ("TEST_ONLY_" if test_only else "") + f"episode_{plan.episode:02d}.mp4"
    temporary = directory / ("encoding_" + name)
    args += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", str(plan.target_seconds),
             "-movflags", "+faststart", "-metadata", "comment=" +
             ("TEST ONLY: synthetic fixtures, not AI footage" if test_only else
              "AI-generated video and synthetic voices; see manifest.json for provenance"), temporary.name]
    command(args, cwd=directory)
    destination = directory.parent / name
    temporary.replace(destination)
    return destination
