from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from capabilities import matrix, route
from common import CinemaError, content_key
from compatibility import snapshots
from continuity_engine import continuity_report, effective_cast
from director_engine import migrate, production_packet
from models import Plan, Settings, VideoProviderConfig, read_model
from video_engine import validate_video_plan


def test_v1_migration_retains_runtime_and_marks_inferred_direction(plan):
    converted = migrate(plan)
    assert converted.version == 2 and plan.version == 1
    assert converted.target_seconds == plan.target_seconds
    assert converted.characters == plan.characters
    assert converted.shots[0].action_beats[-1].end == plan.shots[0].duration
    packet = production_packet(converted)
    assert packet["continuity"]["status"] == "needs_review"
    assert "inferred" in packet["notes"][-1]


def test_action_beat_gaps_and_out_of_frame_regions_rejected(plan):
    data = plan.model_dump()
    data["shots"][0]["action_beats"] = [{"start": 0, "end": 0.5, "action": "turn head"},
                                        {"start": 0.75, "end": 2, "action": "open the door"}]
    with pytest.raises(ValidationError, match="temporal"):
        Plan.model_validate(data)
    data["shots"][0]["action_beats"] = []
    data["shots"][0]["subject_regions"] = [{"box": [0.8, 0, 0.4, 1]}]
    with pytest.raises(ValidationError, match="inside"):
        Plan.model_validate(data)


def test_continuity_change_requires_specific_declared_reason(plan):
    from models import ContinuityState
    first = plan.shots[0].model_copy(deep=True)
    second = first.model_copy(update={"id": "s002"}, deep=True)
    first.scene_id = second.scene_id = "office"
    first.continuity_out = ContinuityState(held_props={"lin_chen": ["phone"]}, axis="door-desk")
    second.continuity_in = ContinuityState(held_props={"lin_chen": []}, axis="desk-door")
    p = plan.model_copy(update={"shots": [first, second], "target_seconds": 4})
    report = continuity_report(p)
    assert len(report["errors"]) == 2
    second.change_reason = "He puts the phone down and camera crosses with a motivated move"
    second.intentional_changes = ["held_props.lin_chen", "axis"]
    assert not continuity_report(p)["errors"]


def test_versioned_costume_needs_dedicated_reference_not_default_image(plan):
    from models import Blocking
    plan.characters[0].costumes = {"evening": "black tuxedo and white shirt"}
    plan.shots[0].blocking = [Blocking(character="lin_chen", wardrobe_version="evening")]
    with pytest.raises(CinemaError, match="front reference"):
        effective_cast(plan, plan.shots[0])
    plan.characters[0].reference_sets = {"evening": {"front": "evening.png"}}
    c = effective_cast(plan, plan.shots[0])[0]
    assert c.wardrobe == "black tuxedo and white shirt" and c.face == plan.characters[0].face
    assert c.references == {"front": "evening.png"}


def test_router_filters_duration_and_controls_before_ranking(plan, settings):
    plan.shots[0].duration = 6
    plan.target_seconds = 6
    plan.shots[0].first_frame, plan.shots[0].last_frame = "first.png", "last.png"
    settings.video = [settings.video[0], VideoProviderConfig(name="runway", model="veo3.1_fast")]
    choices, skipped = route(plan, plan.shots[0], settings)
    assert [c.model for c, _ in choices] == ["veo3.1_fast"]
    assert "last frame" in skipped[0]["reason"]


def test_router_purpose_cost_preferences_and_same_vendor_models(plan, settings):
    settings.video = [VideoProviderConfig(name="runway", model="gen4.5", purposes=["dialogue"]),
                      VideoProviderConfig(name="runway", model="gen4_turbo", purposes=["action"])]
    settings.routing_policy = "purpose"
    plan.shots[0].purpose = "action"
    assert route(plan, plan.shots[0], settings)[0][0][0].model == "gen4_turbo"
    settings.ceilings_usd["runway:video:gen4_turbo"] = 0.01
    settings.routing_policy = "cost"
    assert route(plan, plan.shots[0], settings)[0][0][0].model == "gen4_turbo"
    plan.shots[0].preferred_model = "gen4.5"
    assert route(plan, plan.shots[0], settings)[0][0][0].model == "gen4.5"


def test_native_audio_never_silently_routes_to_silent_model(plan, settings):
    plan.shots[0].native_audio = "preserve"
    with pytest.raises(CinemaError, match="native audio"):
        validate_video_plan(plan, settings, require_keys=False)


def test_full_default_v2_packet_is_varied_complete_and_capable(tmp_path):
    root = Path(__file__).resolve().parents[1]
    plan = read_model(root / "assets/episode01.plan.json", Plan)
    settings = read_model(root / "assets/config.example.json", Settings)
    assert plan.version == 2 and len({s.duration for s in plan.shots}) >= 4
    assert plan.target_seconds == 180 and len(plan.shots) == 30
    assert all(len(s.action_beats) == 3 and s.blocking and s.scene_id for s in plan.shots)
    packet = production_packet(plan, tmp_path)
    assert packet["story"]["cliffhanger"] and not packet["continuity"]["errors"]
    assert not packet["review_items"]
    assert (tmp_path / "edit_decision_list.json").is_file()
    assert len(validate_video_plan(plan, settings, False)) == 30
    assert all(m["documentation"].startswith("https://") and m["async_tasks"] for m in matrix())


def test_v1_bindings_keep_old_shape_but_new_settings_cannot_hide(plan, settings):
    old = snapshots(plan, settings)
    assert "scenes" not in old["plan"] and "motion_review" not in old["settings"]
    assert "_v2_extensions_sha256" not in old["plan"]
    settings.routing_policy = "cost"
    assert content_key(old) != content_key(snapshots(plan, settings))
    plan.shots[0].focus = "eyes"
    assert "_v2_extensions_sha256" in snapshots(plan, Settings())["plan"]


def test_v2_story_planner_has_full_episode_output_allowance_and_stable_cache(tmp_path, plan, settings):
    from common import write_json
    from state import Ledger
    from storyboard_engine import plan_story
    calls = []
    class Planner:
        def response_json(self, prompt, output, model, images=(), max_tokens=16000):
            calls.append({"prompt": prompt, "max_tokens": max_tokens})
            write_json(output, migrate(plan).model_dump())
            return {"evidence": "offline_mock_planner"}
    ledger = Ledger(tmp_path / "tasks.db", 10, True)
    result = plan_story("An employee defends himself", 2, "live_action", settings, ledger,
                        tmp_path / "plan.json", Planner())
    resumed = plan_story("An employee defends himself", 2, "live_action", settings, ledger,
                         tmp_path / "other.json", Planner())
    assert result.version == 2 and resumed == result
    assert len(calls) == 1 and calls[0]["max_tokens"] == 32768
    assert "schema version 2" in calls[0]["prompt"] and "Vary shot durations" in calls[0]["prompt"]
    assert ledger.summary()["reserved_ceiling_usd"] == 0.1
    ledger.close()
