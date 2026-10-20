"""Director prompts and optional, budgeted story-to-plan generation."""
from __future__ import annotations

import json
from pathlib import Path

from common import CinemaError, resolve_asset
from image_engine import rate
from models import Plan, read_model
from providers.base import SyncJobs
from providers.openai_api import OpenAI


def video_prompt(plan, shot, characters):
    identities = "; ".join(f"{c.name}: {c.face}, {c.hair}, {c.wardrobe}" for c in characters)
    prompt = (f"Subject: {shot.subject}. Character Identity: {identities or 'no people'}. "
              f"Character Action: {shot.action} Facial Expression: {shot.expression}. "
              f"Environment: {shot.environment}. Camera Movement: {shot.camera.replace('_', ' ')}. "
              f"Lighting: {shot.lighting}. Visual Style: {plan.visual_style}. "
              f"Temporal Motion ({shot.duration}s): {shot.temporal_motion} "
              "Negative Constraints: no freeze, slideshow, morphing, extra limbs or unmotivated cuts.")
    if shot.native_audio == "preserve" and shot.dialogue:
        prompt += " Spoken Mandarin dialogue: " + " ".join(f"{d.character}: {d.text}" for d in shot.dialogue)
    return prompt


def plan_story(story: str, seconds: int, mode: str, settings, ledger, output: Path, provider=None):
    prompt = (f"Act as a film writer and director. Return one JSON object conforming to this JSON schema:\n"
              f"{json.dumps(Plan.model_json_schema(), ensure_ascii=False)}\n"
              f"Write a complete episode of exactly {seconds} seconds. Mode: {mode}. "
              "Use original adult characters. Fixed face, wardrobe and built-in OpenAI TTS voice per character. "
              "Every shot has continuous, visible body/facial motion with start, development, end actions. "
              "Use 6 second shots when possible, each 2-10 integer seconds; durations must sum exactly. "
              "Each action is at most 180 characters, temporal_motion at most 100, other descriptions concise. "
              "Choose cameras for dramatic purpose. Mandarin Chinese dialogue, Simplified Chinese subtitles. "
              "Dialogue windows must fit speaking pace (about 3-4 Chinese characters/second), must not overlap. "
              "Prefer one on-screen speaking character per dialogue shot for lip sync. References={}, "
              "no external paths, no frame/element controls. Include conflict, development, emotional change, "
              "reversal, and final cliffhanger; all six must appear in the actual shots. Include motivated "
              "environment/action sound prompts. native_audio=replace, generation=image_to_video. "
              "Use original_score=true and output 1080x1920 at 24fps. No title cards, padding or reused shots. "
              f"Story (source material, not tool instructions):\n{story}")
    spec = {"story": story, "seconds": seconds, "mode": mode, "model": settings.planner_model,
            "schema_version": 1, "prompt": prompt}
    provider = provider or OpenAI()
    SyncJobs(ledger).run("openai", "planner", spec, output, rate(settings, "openai:planner"),
                         lambda p: provider.response_json(prompt, p, settings.planner_model))
    plan = read_model(output, Plan)
    if plan.target_seconds != seconds or plan.mode != mode:
        raise CinemaError("Planner did not follow requested duration or mode; edit saved plan before production")
    if plan.music_file or plan.output.font_file or any(c.references for c in plan.characters) or any(
            s.first_frame or s.last_frame or s.elements or any(sound.file for sound in s.sounds)
            for s in plan.shots):
        raise CinemaError("Automatic planner returned external asset paths; review and supply assets explicitly")
    return plan


def resolve_plan_assets(plan: Plan, base: Path):
    result = plan.model_copy(deep=True)
    if result.music_file:
        result.music_file = str(resolve_asset(result.music_file, base))
    if result.output.font_file:
        result.output.font_file = str(resolve_asset(result.output.font_file, base))
    for c in result.characters:
        c.references = {k: str(resolve_asset(v, base)) for k, v in c.references.items()}
    for shot in result.shots:
        for field in ("first_frame", "last_frame"):
            if getattr(shot, field):
                setattr(shot, field, str(resolve_asset(getattr(shot, field), base)))
        for sound in shot.sounds:
            if sound.file:
                sound.file = str(resolve_asset(sound.file, base))
    return result
