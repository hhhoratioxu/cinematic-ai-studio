"""Compile a reviewable production packet and migrate old plans without paid calls."""
from __future__ import annotations

from common import write_json
from continuity_engine import continuity_report
from models import Plan


def production_packet(plan, directory=None):
    cursor, shots, dialogue = 0, [], []
    review = []
    for shot in plan.shots:
        shots.append({"id": shot.id, "scene": shot.scene_id, "in": cursor,
                      "out": cursor + shot.duration, "duration": shot.duration,
                      "story_beat": shot.story_beat, "action": shot.action,
                      "temporal_actions": [b.model_dump() for b in shot.action_beats],
                      "blocking": [b.model_dump() for b in shot.blocking], "focus": shot.focus,
                      "camera": shot.camera, "camera_instructions": shot.camera_instructions,
                      "lighting": shot.lighting, "emotion": shot.expression,
                      "direction": shot.director_instructions, "edit": shot.edit.model_dump(),
                      "source_asset_id": shot.id, "motion_policy": shot.motion_policy})
        for line in shot.dialogue:
            dialogue.append({**line.model_dump(), "shot": shot.id,
                             "start": cursor + line.start, "end": cursor + line.end})
        if not shot.action_beats:
            review.append(f"{shot.id}: start/development/end are prose only")
        if shot.edit.kind == "action_match" and not (shot.edit.entry_action and shot.edit.exit_action):
            review.append(f"{shot.id}: action-match lacks entry/exit action")
        cursor += shot.duration
    beats = {s.story_beat for s in plan.shots}
    for beat in ("conflict", "reversal", "climax", "cliffhanger"):
        if beat not in beats:
            review.append(f"Story beat {beat} has not been assigned to a shot")
    packet = {"schema_version": 2, "title": plan.title, "runtime": cursor,
              "story": plan.story_analysis.model_dump(), "notes": plan.director_notes,
              "shots": shots, "dialogue": dialogue, "music_cues": [c.model_dump() for c in plan.music_cues],
              "duration_rhythm": [s.duration for s in plan.shots], "review_items": review,
              "continuity": continuity_report(plan), "observed_performance": "Pending"}
    if directory:
        write_json(directory / "director_plan.json", packet)
        write_json(directory / "scene_bible.json", [s.model_dump() for s in plan.scenes])
        write_json(directory / "continuity_report.json", packet["continuity"])
        write_json(directory / "edit_decision_list.json", shots)
        write_json(directory / "dialogue_plan.json", dialogue)
    return packet


def migrate(plan):
    if plan.version == 2:
        return plan.model_copy(deep=True)
    data = plan.model_dump()
    data["version"] = 2
    data["director_notes"].append("Migrated from v1: inferred temporal beats require director review; scenes are unspecified.")
    for shot in data["shots"]:
        d = shot["duration"]
        shot["action_beats"] = [
            {"start": 0, "end": round(d / 3, 6), "action": shot["action"]},
            {"start": round(d / 3, 6), "end": round(d * 2 / 3, 6), "action": shot["temporal_motion"]},
            {"start": round(d * 2 / 3, 6), "end": d, "action": "Maintain the planned end pose; director to confirm."}]
    return Plan.model_validate(data)
