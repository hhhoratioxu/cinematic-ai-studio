"""Procedural non-narrative data for tests, never a default production project."""
from __future__ import annotations

from models import Character, Plan


def generic_character(identifier="actor_a", voice="cedar"):
    return Character(id=identifier, name=f"Technical subject {identifier}", age=30,
        face="synthetic oval face", hair="short neutral hair", build="neutral adult proportions",
        wardrobe="plain gray calibration outfit", temperament="neutral test expression", voice=voice,
        style="synthetic calibration subject")


def generic_plan(shot_count=30):
    cast = [generic_character(identifier, voice) for identifier, voice in
            (("actor_a", "cedar"), ("actor_b", "marin"), ("actor_c", "onyx"))]
    state = {"layout": "fixed calibration grid", "time_of_day": "controlled test lighting",
             "lighting": "constant neutral fill", "axis": "reference marks A-B",
             "positions": {c.id: pos for c, pos in zip(cast, ("left", "center", "right"))},
             "gazes": {c.id: "reference mark" for c in cast},
             "held_props": {c.id: [] for c in cast}, "costumes": {c.id: "default" for c in cast},
             "hair": {c.id: c.hair for c in cast}, "behavior": {c.id: "calibration gesture" for c in cast}}
    shots = []
    for index in range(shot_count):
        duration = (3, 4, 5, 7, 8, 9)[index % 6]
        character = cast[index % len(cast)]
        start, middle = round(duration / 3, 3), round(duration * 2 / 3, 3)
        shots.append({"id": f"test_s{index + 1:03d}", "characters": [character.id], "duration": duration,
            "subject": "Synthetic motion calibration subject", "action": "Raise a hand, turn toward a reference mark, then lower the hand.",
            "expression": "neutral calibration", "environment": "plain calibration grid, no story setting",
            "camera": ("wide", "medium", "close_up")[index % 3], "lighting": "constant neutral fill",
            "temporal_motion": "The three calibration gestures occur in sequence over the complete interval.",
            "continuity": "Preserve calibration grid and neutral outfit", "scene_id": "test_grid",
            "blocking": [{"character": character.id, "position": state["positions"][character.id], "gaze": "reference mark"}],
            "action_beats": [{"start": 0, "end": start, "action": "Raise the left hand"},
                             {"start": start, "end": middle, "action": "Turn toward the reference mark"},
                             {"start": middle, "end": duration, "action": "Lower the hand"}],
            "focus": "Calibration subject", "camera_instructions": "Keep the reference axis",
            "director_instructions": "Technical schema fixture only",
            "story_beat": ("conflict", "development", "reversal", "climax", "cliffhanger")[index % 5],
            "continuity_in": state, "continuity_out": state})
    analysis = {name: "Non-narrative schema field fixture" for name in
                ("logline", "mainline", "conflict", "reversal", "climax", "cliffhanger")}
    return Plan.model_validate({"version": 2, "title": "Synthetic multi-shot schema fixture",
        "mode": "live_action", "target_seconds": sum(s["duration"] for s in shots),
        "characters": [c.model_dump() for c in cast], "shots": shots, "story_analysis": analysis,
        "director_notes": ["Test data; no user story or default production"],
        "scenes": [{"id": "test_grid", "location": "test grid", "layout": state["layout"],
                    "time_of_day": state["time_of_day"], "lighting": state["lighting"]}]})
