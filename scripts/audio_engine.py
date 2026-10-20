"""Scheduled Mandarin voices, owned/licensed sounds, and an original ambient score."""
from __future__ import annotations

import array
import math
import wave
from pathlib import Path

from common import CinemaError, command, content_key, media_tool, write_json
from image_engine import rate
from providers.base import AsyncJobs, SyncJobs
from providers.openai_api import OpenAI
from providers.runway import Runway
from quality_control import probe


def original_score(path: Path, seconds: float):
    """An original procedural ambient chord bed, explicitly not AI-composed music."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = 22050
    chords = [(130.81, 155.56, 196.0), (103.83, 130.81, 155.56),
              (116.54, 146.83, 174.61), (98.0, 123.47, 146.83)]
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, sr, 0, "NONE", "not compressed"))
        for second in range(math.ceil(seconds)):
            samples = array.array("h")
            for i in range(min(sr, int((seconds - second) * sr))):
                t = second + i / sr
                frequencies = chords[int(t // 6) % len(chords)]
                fade = min(1.0, t / 2, max(0, seconds - t) / 2)
                chord_fade = min(1.0, (t % 6) / 0.3, (6 - t % 6) / 0.3)
                sample = sum(math.sin(2 * math.pi * hz * t) for hz in frequencies) / 3
                samples.append(int(6000 * sample * fade * chord_fade))
            if __import__("sys").byteorder != "little":
                samples.byteswap()
            f.writeframes(samples.tobytes())
    return path


class AudioEngine:
    def __init__(self, settings, ledger, provider=None, jobs=None):
        self.settings = settings
        self.ledger = ledger
        self.provider = provider
        self.jobs = jobs or AsyncJobs(ledger, settings.poll_seconds, settings.task_timeout_seconds)

    def dialogue(self, shot, characters, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        rendered = []
        by_id = {c.id: c for c in characters}
        if shot.native_audio == "preserve":
            return self.silence(shot.duration, directory / "dialogue.wav"), []
        for i, line in enumerate(shot.dialogue):
            voice = by_id[line.character].voice
            instructions = f"Speak in natural Mandarin Chinese. Emotion and delivery: {line.emotion}."
            spec = {"text": line.text, "voice": voice, "instructions": instructions,
                    "model": self.settings.tts_model}
            raw = directory / f"tts_{content_key(spec)[:16]}.wav"
            api = self.provider or OpenAI()
            SyncJobs(self.ledger).run("openai", "tts", spec, raw, rate(self.settings, "openai:tts"),
                                     lambda p: api.speech(line.text, voice, instructions, p,
                                                          self.settings.tts_model))
            info = probe(raw, self.settings)
            if not info["audio"] or info["duration"] <= 0:
                raise CinemaError(f"{shot.id}: invalid TTS audio")
            window = line.end - line.start
            speed = max(1.0, info["duration"] / window)
            if speed > 1.20:
                raise CinemaError(f"{shot.id}: dialogue {i} needs {info['duration']:.2f}s but has {window:.2f}s; "
                                  "shorten text or revise plan, no truncation or extreme speed-up")
            cooked = directory / f"line_{i:03d}.wav"
            command([media_tool("ffmpeg", self.settings.ffmpeg), "-v", "error", "-y", "-i", str(raw),
                     "-af", f"atempo={speed:.8f},loudnorm=I=-16:TP=-1.5:LRA=11",
                     "-ar", "48000", "-ac", "2", str(cooked)])
            rendered.append({"file": cooked, "start": line.start,
                             "end": min(line.end, line.start + info["duration"] / speed),
                             "character": line.character, "text": line.text,
                             "speed_factor": speed, "gain_db": 0})
        output = self.mix(shot.duration, rendered, directory / "dialogue.wav")
        write_json(directory / "dialogue_timing.json", [{**r, "file": str(r["file"])} for r in rendered])
        return output, rendered

    def silence(self, seconds, output):
        return self.mix(seconds, [], output)

    def mix(self, seconds, tracks, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        args = [media_tool("ffmpeg", self.settings.ffmpeg), "-v", "error", "-y", "-f", "lavfi",
                "-i", "anullsrc=r=48000:cl=stereo"]
        filters = []
        labels = ["[0:a]"]
        for i, track in enumerate(tracks, 1):
            args += ["-i", str(track["file"])]
            ms = round(track["start"] * 1000)
            filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,"
                           f"volume={track.get('gain_db', 0)}dB,adelay={ms}|{ms}[a{i}]")
            labels.append(f"[a{i}]")
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0,"
                       f"atrim=duration={seconds},alimiter=limit=0.95[out]")
        args += ["-filter_complex", ";".join(filters), "-map", "[out]", "-t", str(seconds),
                 "-c:a", "pcm_s16le", str(output)]
        command(args)
        return output

    def sound_tracks(self, shot, directory):
        tracks = []
        for sound in shot.sounds:
            if sound.file:
                output = Path(sound.file)
            else:
                spec = {"kind": "sfx", "model": "eleven_text_to_sound_v2", "prompt": sound.prompt,
                        "duration": sound.duration}
                output, _ = self.jobs.run(Runway(), spec, directory / f"sfx_{sound.id}.mp3",
                                          rate(self.settings, "runway:sfx", sound.duration), kind="sfx")
            info = probe(output, self.settings)
            if not info["audio"]:
                raise CinemaError(f"{shot.id}: sound {sound.id} is not valid audio")
            tracks.append({"file": output, "start": sound.start, "gain_db": sound.gain_db})
        return tracks


def srt_time(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def wrap_subtitle(text: str, max_units: int, font=None, max_pixels=None):
    text = text.replace("\r", " ").replace("\n", " ").strip()
    lines, line, units = [], "", 0
    for char in text:
        width = 2 if __import__("unicodedata").east_asian_width(char) in ("F", "W") else 1
        too_wide = (font.getlength(line + char) > max_pixels) if font and max_pixels else units + width > max_units
        if too_wide:
            lines.append(line)
            line, units = "", 0
        line += char
        units += width
    if line:
        lines.append(line)
    if len(lines) > 2:
        raise CinemaError("Subtitle exceeds two safe lines; shorten dialogue or split its timing")
    return "\n".join(lines)


def subtitles(plan, output_dir: Path, timings: dict | None = None):
    from common import atomic_bytes
    width, height = plan.output.width, plan.output.height
    font_size = max(16, round(height * 0.026))
    margin_x = round(width * 0.08)
    margin_y = round(height * 0.08)
    max_units = int((width - 2 * margin_x) / font_size * 2 * 0.85)
    font = None
    if plan.output.font_file:
        from PIL import ImageFont
        font = ImageFont.truetype(plan.output.font_file, font_size)
    events, cursor, index = [], 0.0, 1
    ass = ("[Script Info]\nScriptType: v4.00+\n" + f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
           "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n" +
           f"Style: Default,{plan.output.font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00181818,&H90000000,"
           f"0,0,0,0,100,100,0,0,1,2,1,2,{margin_x},{margin_x},{margin_y},1\n"
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    def ass_time(t):
        cs = round(t * 100)
        return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"
    timing_report = []
    for shot in plan.shots:
        actual = (timings or {}).get(shot.id, [])
        for i, line in enumerate(shot.dialogue):
            end = actual[i]["end"] if i < len(actual) else line.end
            start = cursor + line.start
            end += cursor
            text = wrap_subtitle(line.text, max_units, font, width - 2 * margin_x - 8)
            events.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
            # Reject ASS overrides rather than letting dialogue alter layout or draw outside the frame.
            safe = text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", "\\N")
            ass += f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{safe}\n"
            timing_report.append({"shot": shot.id, "speaker": line.character, "start": start, "end": end,
                                  "text": line.text})
            index += 1
        cursor += shot.duration
    atomic_bytes(output_dir / "subtitles.srt", ("\n".join(events)).encode("utf-8"))
    atomic_bytes(output_dir / "subtitles.ass", ass.encode("utf-8"))
    write_json(output_dir / "subtitle_layout.json", {"safe_margin_x": margin_x, "safe_margin_y": margin_y,
               "font_size": font_size, "max_lines": 2, "estimated_fit": True,
               "measured_with_local_font": bool(font),
               "rendered_glyph_bounds": "requires visual review", "events": timing_report})
    return output_dir / "subtitles.srt", output_dir / "subtitles.ass"
