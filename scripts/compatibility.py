"""Keep v0.1 task fingerprints usable when reopening a version-1 plan."""
from __future__ import annotations

CHARACTER_V1 = set("id name age face hair build wardrobe temperament voice style references".split())
SHOT_V1 = set("id characters duration subject action expression environment camera lighting temporal_motion continuity dialogue sounds first_frame last_frame elements generation native_audio".split())
PLAN_V1 = set("version title episode mode visual_style language target_seconds output characters shots music_file music_license original_score".split())
SETTINGS_V1 = set("video image_model image_size image_quality planner_model tts_model vision_model vision_qc lipsync lipsync_model max_concurrency max_attempts poll_seconds task_timeout_seconds ceilings_usd ffmpeg ffprobe".split())


def character_snapshot(character, version):
    data = character.model_dump()
    return {k: v for k, v in data.items() if k in CHARACTER_V1} if version == 1 else data


def snapshots(plan, settings):
    p, s = plan.model_dump(), settings.model_dump()
    if plan.version == 1:
        p = {k: v for k, v in p.items() if k in PLAN_V1}
        p["characters"] = [character_snapshot(c, 1) for c in plan.characters]
        p["shots"] = [{k: v for k, v in shot.items() if k in SHOT_V1} for shot in p["shots"]]
        for shot in p["shots"]:
            shot["sounds"] = [{k: v for k, v in sound.items() if k not in ("fade_in", "fade_out")}
                              for sound in shot["sounds"]]
        s = {k: v for k, v in s.items() if k in SETTINGS_V1}
        s["video"] = [{k: v for k, v in config.items() if k in ("name", "model", "mode")} for config in s["video"]]
        def extra(model, old):
            dumped = model.model_dump()
            return {name: dumped[name] for name, field in model.__class__.model_fields.items()
                    if name not in old and getattr(model, name) != field.get_default(call_default_factory=True)}
        extension = {"plan": extra(plan, PLAN_V1), "settings": extra(settings, SETTINGS_V1),
                     "shots": {shot.id: extra(shot, SHOT_V1) for shot in plan.shots if extra(shot, SHOT_V1)},
                     "characters": {c.id: extra(c, CHARACTER_V1) for c in plan.characters if extra(c, CHARACTER_V1)},
                     "video": [extra(c, {"name", "model", "mode"}) for c in settings.video]}
        # Only non-default v2 features add a new binding. Old runs retain byte-identical inputs.
        if any(extension[k] for k in ("plan", "settings", "shots", "characters")) or any(extension["video"]):
            from common import content_key
            p["_v2_extensions_sha256"] = content_key(extension)
    return {"plan": p, "settings": s}
