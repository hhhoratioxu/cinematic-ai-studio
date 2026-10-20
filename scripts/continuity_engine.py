"""Explicit story state continuity, without treating planned state as observed footage."""
from __future__ import annotations

from common import CinemaError


def effective_cast(plan, shot, characters=None):
    cast = []
    for character in characters if characters is not None else plan.characters:
        if character.id not in shot.characters:
            continue
        block = next((b for b in shot.blocking if b.character == character.id), None)
        version = block.wardrobe_version if block else character.wardrobe_version
        if version == "default":
            cast.append(character)
        else:
            if version not in character.costumes:
                raise CinemaError(f"{shot.id}: unknown costume {character.id}/{version}")
            refs = character.reference_sets.get(version, {})
            # Never feed a contradictory default costume image as a versioned scene reference.
            if not refs.get("front"):
                raise CinemaError(f"{shot.id}: prepare an explicit front reference for costume {character.id}/{version}")
            cast.append(character.model_copy(update={"wardrobe": character.costumes[version],
                                                      "wardrobe_version": version, "references": refs}))
    return cast


def continuity_report(plan):
    errors, review, changes = [], [], []
    previous = None
    for shot in plan.shots:
        state_in = shot.continuity_in.model_dump(exclude_defaults=True)
        state_out = shot.continuity_out.model_dump(exclude_defaults=True)
        if plan.version == 2:
            if not shot.scene_id or not state_in or not state_out:
                review.append(f"{shot.id}: missing scene or continuity state")
            if not shot.blocking and shot.characters:
                review.append(f"{shot.id}: blocking is unspecified")
        if previous and previous.scene_id and previous.scene_id == shot.scene_id:
            before = previous.continuity_out.model_dump(exclude_defaults=True)
            for field in set(before) & set(state_in):
                left, right = before[field], state_in[field]
                if isinstance(left, dict) and isinstance(right, dict):
                    differences = [f"{field}.{key}" for key in set(left) & set(right) if left[key] != right[key]]
                else:
                    differences = [field] if left != right else []
                for change in differences:
                    intentional = change in shot.intentional_changes or field in shot.intentional_changes
                    detail = {"from": previous.id, "to": shot.id, "field": change,
                              "intentional": intentional, "reason": shot.change_reason}
                    changes.append(detail)
                    if not intentional:
                        errors.append(f"{shot.id}: unexplained continuity change {change}")
        for field in set(state_in) & set(state_out):
            if state_in[field] != state_out[field] and not shot.action_beats:
                review.append(f"{shot.id}: {field} changes inside shot; verify motivated action")
        previous = shot
    if plan.version == 1:
        review.append("Version 1 has no structured continuity guarantee; migrate or review manually")
    return {"status": "blocked" if errors else "needs_review" if review else "planned_consistent",
            "errors": errors, "review_items": review, "changes": changes,
            "evidence": "planned_states_only", "observed_continuity": "Pending"}


def require_continuity(plan):
    report = continuity_report(plan)
    if report["errors"]:
        raise CinemaError("Continuity: " + "; ".join(report["errors"]))
    return report
