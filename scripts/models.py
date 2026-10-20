"""Validated on-disk contracts shared by the CLI, Codex, and providers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class Character(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    name: str = Field(min_length=1)
    age: int = Field(ge=0, le=120)
    face: str = Field(min_length=3)
    hair: str = Field(min_length=3)
    build: str = Field(min_length=3)
    wardrobe: str = Field(min_length=3)
    temperament: str = Field(min_length=3)
    voice: Literal["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage",
                   "shimmer", "verse", "marin", "cedar"] = "cedar"
    style: str = "original cinematic character"
    references: dict[str, str] = Field(default_factory=dict)

    def identity(self) -> str:
        return (f"{self.id} ({self.name}, {self.age}): {self.face}; {self.hair}; "
                f"{self.build}; wearing {self.wardrobe}; {self.temperament}; {self.style}")


class Dialogue(Contract):
    character: str
    text: str = Field(min_length=1, max_length=300)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    emotion: str = "natural, Mandarin Chinese"
    delivery: Literal["onscreen", "offscreen", "narration"] = "onscreen"


class Sound(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    prompt: str = Field(min_length=3, max_length=1000)
    start: float = Field(ge=0)
    duration: float = Field(ge=0.5, le=30)
    gain_db: float = Field(default=-18, ge=-60, le=0)
    file: str | None = None
    license: str | None = None


class Shot(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    characters: list[str]
    duration: int = Field(ge=2, le=10)
    subject: str = Field(min_length=3, max_length=120)
    action: str = Field(min_length=20, max_length=380)
    expression: str = Field(min_length=3, max_length=100)
    environment: str = Field(min_length=3, max_length=180)
    camera: Literal["establishing", "wide", "medium", "close_up", "extreme_close_up", "over_shoulder",
                    "tracking", "dolly_in", "dolly_out", "pan", "tilt", "handheld", "low_angle", "high_angle"]
    lighting: str = Field(min_length=3, max_length=100)
    temporal_motion: str = Field(min_length=15, max_length=220)
    continuity: str = Field(min_length=3, max_length=180)
    dialogue: list[Dialogue] = Field(default_factory=list)
    sounds: list[Sound] = Field(default_factory=list)
    first_frame: str | None = None
    last_frame: str | None = None
    elements: list[str] = Field(default_factory=list)
    generation: Literal["image_to_video", "text_to_video"] = "image_to_video"
    native_audio: Literal["preserve", "mute", "replace"] = "replace"

    @model_validator(mode="after")
    def check_timeline(self):
        lines = sorted(self.dialogue, key=lambda d: d.start)
        for i, line in enumerate(lines):
            if line.end <= line.start or line.end > self.duration:
                raise ValueError(f"{self.id}: dialogue exceeds shot or has nonpositive duration")
            if i and line.start < lines[i - 1].end:
                raise ValueError(f"{self.id}: overlapping dialogue is not supported")
        if self.dialogue and self.native_audio == "mute":
            raise ValueError("mute discards dialogue; choose preserve or replace")
        for sound in self.sounds:
            if sound.start + sound.duration > self.duration + 0.001:
                raise ValueError(f"{self.id}: sound exceeds shot")
            if sound.file and not sound.license:
                raise ValueError("imported audio needs a license/rights declaration")
        if self.last_frame and not self.first_frame:
            raise ValueError("last_frame needs first_frame")
        if self.generation == "text_to_video" and (self.first_frame or self.last_frame or self.elements):
            raise ValueError("text_to_video cannot silently discard frame/element controls")
        return self


class Output(Contract):
    width: int = Field(default=1080, ge=128, le=3840, multiple_of=2)
    height: int = Field(default=1920, ge=128, le=3840, multiple_of=2)
    fps: int = Field(default=24, ge=12, le=60)
    burn_subtitles: bool = True
    font_file: str | None = None
    font_name: str = "Noto Sans CJK SC"
    crf: int = Field(default=18, ge=12, le=28)
    grade: Literal["neutral", "warm", "cool"] = "neutral"


class Plan(Contract):
    version: Literal[1] = 1
    title: str = Field(min_length=1)
    episode: int = Field(default=1, ge=1, le=999)
    mode: Literal["live_action", "anime", "motion_comic", "ai_drama"] = "live_action"
    visual_style: str = "realistic cinematic live action, original actors, restrained performances"
    language: str = "zh-CN"
    target_seconds: int = Field(ge=2, le=3600)
    output: Output = Field(default_factory=Output)
    characters: list[Character]
    shots: list[Shot] = Field(min_length=1)
    music_file: str | None = None
    music_license: str | None = None
    original_score: bool = True

    @model_validator(mode="after")
    def check_coverage(self):
        ids = [c.id for c in self.characters]
        if len(ids) != len(set(ids)) or len({s.id for s in self.shots}) != len(self.shots):
            raise ValueError("character and shot IDs must be unique")
        if sum(s.duration for s in self.shots) != self.target_seconds:
            raise ValueError("shot durations must exactly cover target_seconds; padding is prohibited")
        for shot in self.shots:
            if not set(shot.characters) <= set(ids):
                raise ValueError(f"{shot.id}: unknown character")
            if any(d.character not in ids for d in shot.dialogue):
                raise ValueError(f"{shot.id}: unknown speaker")
            if any(d.delivery == "onscreen" and d.character not in shot.characters for d in shot.dialogue):
                raise ValueError(f"{shot.id}: onscreen speaker absent from shot")
        if self.music_file and not self.music_license:
            raise ValueError("music_file requires music_license")
        return self


class VideoProviderConfig(Contract):
    name: Literal["runway", "kling"]
    model: str
    mode: Literal["std", "pro"] = "pro"


class Settings(Contract):
    video: list[VideoProviderConfig] = Field(default_factory=lambda: [
        VideoProviderConfig(name="runway", model="gen4.5")])
    image_model: str = "gpt-image-1.5"
    image_size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1536"
    image_quality: Literal["low", "medium", "high"] = "medium"
    planner_model: str = "gpt-4.1-mini"
    tts_model: Literal["gpt-4o-mini-tts"] = "gpt-4o-mini-tts"
    vision_model: str = "gpt-4.1-mini"
    vision_qc: bool = True
    lipsync: Literal["sync", "off"] = "sync"
    lipsync_model: Literal["lipsync-2", "lipsync-2-pro"] = "lipsync-2"
    max_concurrency: int = Field(default=2, ge=1, le=8)
    max_attempts: int = Field(default=2, ge=1, le=4)
    poll_seconds: float = Field(default=5, ge=5, le=60)
    task_timeout_seconds: int = Field(default=1800, ge=10, le=14400)
    ceilings_usd: dict[str, float] = Field(default_factory=dict)
    # Units: video/lipsync/sfx per second; image/planner/vision/tts per call.
    ffmpeg: str | None = None
    ffprobe: str | None = None

    @model_validator(mode="after")
    def validate_rates(self):
        import math
        if any(not math.isfinite(v) or v <= 0 for v in self.ceilings_usd.values()):
            raise ValueError("cost ceilings must be positive finite USD numbers")
        if not self.video or len({v.name for v in self.video}) != len(self.video):
            raise ValueError("configure one or more distinct video providers")
        return self


def read_model(path: Path, cls):
    return cls.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
