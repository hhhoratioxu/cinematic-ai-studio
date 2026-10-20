"""Conservative, documented adapter capabilities; routing never invents model quality scores."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from common import CinemaError


@dataclass(frozen=True)
class Capability:
    provider: str
    model: str
    text_to_video: bool
    first_frame: bool
    last_frame: bool
    elements: bool
    durations: tuple[int, ...]
    ratios: tuple[str, ...]
    native_dimensions: tuple[str, ...]
    native_audio: bool
    documentation: str
    recovery: str = "Poll a recorded task ID; uncertain POST stops until reconciliation"
    async_tasks: bool = True
    reference_images: str = "First frame only; identity in other images is not an API guarantee"
    cost: str = "User-reviewed per-model ceiling per generated second; invoice remains separate"
    checked: str = "2026-10-20"


RUNWAY = "https://docs.dev.runwayml.com/api/"
KLING = "https://kling.ai/document-api/api/video/2-6/image-to-video/legacy"
CAPABILITIES = (
    Capability("runway", "gen4.5", True, True, False, False, tuple(range(2, 11)),
               ("9:16", "16:9", "1:1", "3:4", "4:3", "33:14"),
               ("720:1280", "1280:720", "960:960", "832:1104", "1104:832", "1584:672"), False, RUNWAY),
    Capability("runway", "gen4_turbo", False, True, False, False, tuple(range(2, 11)),
               ("9:16", "16:9", "1:1", "3:4", "4:3", "33:14"),
               ("720:1280", "1280:720", "960:960", "832:1104", "1104:832", "1584:672"), False, RUNWAY),
    *(Capability("runway", m, True, True, True, False, (4, 6, 8), ("9:16", "16:9"),
                 ("720:1280", "1280:720", "1080:1920", "1920:1080"), True, RUNWAY)
      for m in ("veo3.1", "veo3.1_fast")),
    Capability("kling", "kling-v2-6", True, True, True, False, (5, 10), ("9:16", "16:9", "1:1"),
               ("Provider/model/mode determined; read actual delivered dimensions from FFprobe",), True, KLING),
    Capability("kling", "kling-v3", True, True, True, True, tuple(range(3, 11)),
               ("9:16", "16:9", "1:1"), ("Provider/model/mode determined; probe every result",), True,
               "https://kling.ai/document-api/api/video/3-0/image-to-video/legacy",
               reference_images="First/last frames and up to 3 existing Element IDs on image-to-video"),
)


def matrix():
    return [asdict(c) for c in CAPABILITIES]


def capability(config):
    for c in CAPABILITIES:
        if (c.provider, c.model) == (config.name, config.model):
            return c
    raise CinemaError(f"Unverified configured model: {config.name}/{config.model}")


def compatible(plan, shot, config):
    import math
    c = capability(config)
    gcd = math.gcd(plan.output.width, plan.output.height)
    ratio = f"{plan.output.width // gcd}:{plan.output.height // gcd}"
    if shot.duration not in c.durations:
        raise CinemaError(f"{c.model} supports adapter durations {c.durations}, got {shot.duration}")
    if ratio not in c.ratios:
        raise CinemaError(f"{c.model} does not support adapter aspect ratio {ratio}")
    if shot.generation == "text_to_video" and not c.text_to_video:
        raise CinemaError(f"{c.model} requires a first frame")
    if shot.generation == "text_to_video" and c.provider == "runway" and ratio not in ("9:16", "16:9"):
        raise CinemaError("Runway text-to-video adapter uses 9:16 or 16:9")
    if shot.last_frame and not c.last_frame:
        raise CinemaError(f"{c.model} does not accept a last frame")
    if shot.elements and (not c.elements or shot.generation != "image_to_video"):
        raise CinemaError(f"{c.model} does not accept these Element controls")
    if shot.native_audio == "preserve" and not c.native_audio:
        raise CinemaError(f"{c.model} has no verified native audio; choose replace or an audio-capable model")
    return c


def route(plan, shot, settings):
    candidates, skipped = [], []
    for i, config in enumerate(settings.video):
        try:
            compatible(plan, shot, config)
        except CinemaError as e:
            skipped.append({"provider": config.name, "model": config.model, "reason": str(e)})
            continue
        preference = int(bool(shot.preferred_provider and config.name != shot.preferred_provider))
        preference += int(bool(shot.preferred_model and config.model != shot.preferred_model))
        rate = settings.ceilings_usd.get(f"{config.name}:video:{config.model}", float("inf"))
        if settings.routing_policy == "cost":
            rank = (preference, rate, -config.priority, i)
        elif settings.routing_policy == "purpose":
            rank = (preference, int(shot.purpose not in config.purposes), -config.priority, i)
        else:
            rank = (preference, i)
        reason = {"policy": settings.routing_policy, "purpose": shot.purpose,
                  "configured_purpose_match": shot.purpose in config.purposes,
                  "priority": config.priority, "preference_penalty": preference,
                  "reviewed_ceiling_per_second_usd": None if rate == float("inf") else rate,
                  "basis": "Verified controls plus user configuration; no inferred model quality ranking"}
        candidates.append((rank, config, reason))
    candidates.sort(key=lambda item: item[0])
    return [(config, reason) for _, config, reason in candidates], skipped
