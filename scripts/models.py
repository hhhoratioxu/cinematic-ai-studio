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
    description: str = ""
    wardrobe_version: str = "default"
    costumes: dict[str, str] = Field(default_factory=dict)
    reference_sets: dict[str, dict[str, str]] = Field(default_factory=dict)
    expression_views: list[str] = Field(default_factory=list)
    story_state: str = ""
    relationships: dict[str, str] = Field(default_factory=dict)
    speech_style: str = ""
    speech_speed: float = Field(default=1, ge=0.8, le=1.2)

    @model_validator(mode="after")
    def check_versions(self):
        import re
        if self.wardrobe_version != "default" and self.wardrobe_version not in self.costumes:
            raise ValueError("a non-default wardrobe_version must exist in costumes")
        if self.wardrobe_version != "default" and self.costumes[self.wardrobe_version] != self.wardrobe:
            raise ValueError("active wardrobe must match its declared costume version")
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", v) for v in self.expression_views):
            raise ValueError("expression view IDs must be safe lowercase identifiers")
        return self

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
    fade_in: float = Field(default=0.03, ge=0, le=5)
    fade_out: float = Field(default=0.1, ge=0, le=5)


class Scene(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    location: str
    layout: str
    time_of_day: str
    lighting: str
    props: list[str] = Field(default_factory=list)
    description: str = ""


class ActionBeat(Contract):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    action: str = Field(min_length=3)


class Blocking(Contract):
    character: str
    position: Literal["left", "center", "right", "offscreen"] = "center"
    gaze: str = ""
    props: list[str] = Field(default_factory=list)
    wardrobe_version: str = "default"
    state: str = ""


class ContinuityState(Contract):
    layout: str = ""
    time_of_day: str = ""
    lighting: str = ""
    axis: str = ""
    positions: dict[str, str] = Field(default_factory=dict)
    gazes: dict[str, str] = Field(default_factory=dict)
    held_props: dict[str, list[str]] = Field(default_factory=dict)
    costumes: dict[str, str] = Field(default_factory=dict)
    hair: dict[str, str] = Field(default_factory=dict)
    behavior: dict[str, str] = Field(default_factory=dict)


class SubjectRegion(Contract):
    character: str | None = None
    # Normalized x, y, width, height in the delivered image.
    box: tuple[float, float, float, float]
    source: Literal["planned", "user", "detector"] = "planned"

    @model_validator(mode="after")
    def in_frame(self):
        x, y, w, h = self.box
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.000001 or y + h > 1.000001:
            raise ValueError("subject region must fit inside the image")
        return self


class Edit(Contract):
    kind: Literal["hard_cut", "reverse_shot", "action_match", "scene_change"] = "hard_cut"
    rationale: str = ""
    entry_action: str = ""
    exit_action: str = ""
    audio_fade: float = Field(default=0, ge=0, le=0.25)


class MusicCue(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    file: str | None = None
    license: str | None = None
    gain_db: float = Field(default=-18, ge=-60, le=0)
    fade_in: float = Field(default=1, ge=0, le=30)
    fade_out: float = Field(default=1, ge=0, le=30)


class StoryAnalysis(Contract):
    logline: str = ""
    mainline: str = ""
    conflict: str = ""
    emotional_arc: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    reversal: str = ""
    climax: str = ""
    cliffhanger: str = ""


class Shot(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    characters: list[str]
    duration: int = Field(ge=2, le=15)
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
    scene_id: str | None = None
    blocking: list[Blocking] = Field(default_factory=list)
    action_beats: list[ActionBeat] = Field(default_factory=list)
    focus: str = ""
    camera_instructions: str = ""
    director_instructions: str = ""
    story_beat: Literal["conflict", "development", "reaction", "foreshadowing", "reversal", "climax",
                        "cliffhanger", "transition"] = "development"
    continuity_in: ContinuityState = Field(default_factory=ContinuityState)
    continuity_out: ContinuityState = Field(default_factory=ContinuityState)
    intentional_changes: list[str] = Field(default_factory=list)
    change_reason: str = ""
    motion_policy: Literal["required", "subtle", "hold", "environment"] = "required"
    subject_regions: list[SubjectRegion] = Field(default_factory=list)
    purpose: Literal["performance", "action", "dialogue", "anime_action", "complex_scene", "continuity",
                     "establishing"] = "performance"
    preferred_provider: Literal["runway", "kling"] | None = None
    preferred_model: str | None = None
    edit: Edit = Field(default_factory=Edit)
    source_video: str | None = None
    source_license: str | None = None

    @model_validator(mode="after")
    def check_timeline(self):
        last_end = 0.0
        for beat in self.action_beats:
            if beat.end <= beat.start or beat.end > self.duration or abs(beat.start - last_end) > 0.00001:
                raise ValueError(f"{self.id}: invalid/overlapping temporal action beats")
            last_end = beat.end
        if self.action_beats and (self.action_beats[0].start != 0 or last_end != self.duration):
            raise ValueError(f"{self.id}: action beats must cover start through end")
        if self.intentional_changes and not self.change_reason:
            raise ValueError("intentional continuity changes need a reason")
        if self.source_video and not self.source_license:
            raise ValueError("imported dynamic footage requires a rights declaration")
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
    version: Literal[1, 2] = 1
    title: str = Field(min_length=1)
    episode: int = Field(default=1, ge=1, le=999)
    mode: Literal["live_action", "anime", "motion_comic", "ai_drama"] = "live_action"
    visual_style: str = ""
    language: str = "zh-CN"
    target_seconds: int = Field(ge=2, le=3600)
    output: Output = Field(default_factory=Output)
    characters: list[Character]
    shots: list[Shot] = Field(min_length=1)
    music_file: str | None = None
    music_license: str | None = None
    original_score: bool = True
    scenes: list[Scene] = Field(default_factory=list)
    story_analysis: StoryAnalysis = Field(default_factory=StoryAnalysis)
    director_notes: list[str] = Field(default_factory=list)
    music_cues: list[MusicCue] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def mode_style_defaults(cls, data):
        if isinstance(data, dict) and not data.get("visual_style"):
            defaults = {
                "live_action": "cinematic live action, original performers, natural skin and body motion",
                "anime": "cinematic animated film, consistent anime design, articulated body and facial animation",
                "motion_comic": "animated motion comic, consistent ink and shading, articulated character motion",
                "ai_drama": "cinematic live action drama, original performers, restrained natural acting"}
            data = {**data, "visual_style": defaults.get(data.get("mode", "live_action"), defaults["live_action"])}
        return data

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
            if shot.scene_id and shot.scene_id not in {s.id for s in self.scenes}:
                raise ValueError(f"{shot.id}: scene is absent from the Scene Bible")
            if any(b.character not in ids for b in shot.blocking):
                raise ValueError(f"{shot.id}: unknown blocking character")
            if any(b.position != "offscreen" and b.character not in shot.characters for b in shot.blocking):
                raise ValueError(f"{shot.id}: visible blocking character is absent from shot")
            for state in (shot.continuity_in, shot.continuity_out):
                for field in ("positions", "gazes", "held_props", "costumes", "hair", "behavior"):
                    if not set(getattr(state, field)) <= set(ids):
                        raise ValueError(f"{shot.id}: continuity contains an unknown character")
            if any(r.character and r.character not in shot.characters for r in shot.subject_regions):
                raise ValueError(f"{shot.id}: subject region references an absent character")
            for block in shot.blocking:
                c = next(c for c in self.characters if c.id == block.character)
                if block.wardrobe_version != "default" and block.wardrobe_version not in c.costumes:
                    raise ValueError(f"{shot.id}: unknown wardrobe version")
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError("Scene IDs must be unique")
        for cue in self.music_cues:
            if cue.end <= cue.start or cue.end > self.target_seconds:
                raise ValueError("music cue must fit within the episode")
            if cue.file and not cue.license:
                raise ValueError("imported music cue needs a rights declaration")
        if self.music_file and not self.music_license:
            raise ValueError("music_file requires music_license")
        return self


class VideoProviderConfig(Contract):
    name: Literal["runway", "kling"]
    model: str
    mode: Literal["std", "pro"] = "pro"
    purposes: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=0, le=100)


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
    routing_policy: Literal["order", "cost", "purpose"] = "order"
    motion_review: bool = True
    motion_sample_fps: int = Field(default=6, ge=2, le=12)
    max_shot_regenerations: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def validate_rates(self):
        import math
        if any(not math.isfinite(v) or v <= 0 for v in self.ceilings_usd.values()):
            raise ValueError("cost ceilings must be positive finite USD numbers")
        if not self.video or len({(v.name, v.model, v.mode) for v in self.video}) != len(self.video):
            raise ValueError("configure one or more distinct provider/model/mode combinations")
        return self


def read_model(path: Path, cls):
    return cls.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
