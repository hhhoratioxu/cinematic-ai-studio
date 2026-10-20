from __future__ import annotations

import json
import shutil

import pytest
from pydantic import ValidationError

from audio_engine import AudioEngine, subtitles, wrap_subtitle
from character_engine import merge_bible, prepare_characters
from common import CinemaError, content_key
from image_engine import ImageEngine
from mock_provider import MockOpenAI, MockVideo
from models import Dialogue, Plan
from pipeline import estimate
from providers.base import AsyncJobs
from quality_control import inspect_video
from run_offline_demo import run as run_demo
from state import Ledger
from video_engine import VideoEngine, decoded_signature, make_spec, validate_video_plan


def test_A_image_generation_and_reference_edit_cache(tmp_path, settings):
    api = MockOpenAI()
    ledger = Ledger(tmp_path / "tasks.db", 2, True)
    engine = ImageEngine(settings, ledger, api)
    first = engine.generate("cinematic original character", tmp_path / "first.png")
    engine.generate("cinematic original character", tmp_path / "different.png")
    side = engine.generate("turn to side", tmp_path / "side.png", [first])
    assert side.is_file() and len(api.calls) == 2
    assert api.calls[1]["references"] == [first]
    ledger.close()


@pytest.mark.parametrize("mode", ["live_action", "anime", "motion_comic", "ai_drama"])
def test_B_C_real_video_route_with_mock_adapter(tmp_path, settings, plan, media_factory, mode):
    plan = Plan.model_validate({**plan.model_dump(), "mode": mode, "visual_style": ""})
    provider = MockVideo()
    ledger = Ledger(tmp_path / "tasks.db", 10, True)
    def download(url, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media_factory(), output)
    jobs = AsyncJobs(ledger, downloader=download)
    engine = VideoEngine(settings, ledger, jobs, {"runway": lambda: provider})
    video, report = engine.generate(plan, plan.shots[0], plan.characters, None, tmp_path / "shot")
    assert inspect_video(video, settings, 2)["technical_pass"]
    assert provider.submissions == 1 and report["evidence"] == "synthetic_test_fixture"
    if mode in ("anime", "motion_comic"):
        assert "articulated" in provider.specs[0]["prompt"]
        assert "live action" not in provider.specs[0]["prompt"]
    ledger.close()


def test_D_character_bible_reuse_and_identity_guard(tmp_path, settings, plan):
    api = MockOpenAI()
    ledger = Ledger(tmp_path / "tasks.db", 10, True)
    engine = ImageEngine(settings, ledger, api)
    first = prepare_characters(plan, engine, tmp_path / "characters", tmp_path)
    second = prepare_characters(plan, engine, tmp_path / "characters", tmp_path)
    assert first[0].references == second[0].references
    assert set(first[0].references) == {"front", "side", "full_body"}
    assert len(api.calls) == 3
    assert api.calls[1]["references"] == [__import__("pathlib").Path(first[0].references["front"])]
    assert merge_bible(plan, first).characters[0].references == first[0].references
    changed = plan.model_copy(deep=True)
    changed.characters[0].voice = "marin"
    with pytest.raises(ValueError, match="changed voice"):
        merge_bible(changed, first)
    ledger.close()


def test_E_multi_voice_chinese_timeline_and_subtitles(tmp_path, settings, plan):
    api = MockOpenAI()
    ledger = Ledger(tmp_path / "tasks.db", 10, True)
    plan.shots[0].dialogue = [Dialogue(character="actor_a", text="测试中文对白", start=0.25, end=1.75)]
    audio, timings = AudioEngine(settings, ledger, api).dialogue(plan.shots[0], plan.characters, tmp_path / "audio")
    assert audio.is_file() and timings[0]["start"] == 0.25
    assert api.calls[0]["voice"] == "cedar" and api.calls[0]["text"] == "测试中文对白"
    srt, ass = subtitles(plan, tmp_path, {plan.shots[0].id: timings})
    assert "00:00:00,250 --> 00:00:00,750" in srt.read_text(encoding="utf-8")
    assert "测试中文对白" in ass.read_text(encoding="utf-8")
    ledger.close()


def test_F_H_complete_timeline_real_ffmpeg_mp4_export(tmp_path):
    result = run_demo(tmp_path)
    assert result["status"] == "offline_pipeline_pass"
    assert result["test_only"] and not result["real_model_generation"]
    assert result["paid_calls"] == 0
    qc = result["technical_qc"]
    assert qc["technical_pass"] and abs(qc["duration"] - 6) < 0.12
    assert (qc["width"], qc["height"], qc["fps"]) == (320, 576, 24)
    assert qc["has_audio"]
    assert "TEST_ONLY_" in result["output"]
    assert not (tmp_path / "episode_01.mp4").exists()
    assert {call["voice"] for call in result["mock_calls"] if call["kind"] == "tts"} == {"cedar", "marin"}


def test_G_qc_rejects_frozen_black_and_bad_duration(settings, media_factory):
    frozen = inspect_video(media_factory(frozen=True), settings, 2)
    black = inspect_video(media_factory(black=True), settings, 2)
    wrong_duration = inspect_video(media_factory(), settings, 5)
    assert "frozen_frames" in frozen["issues"] and not frozen["technical_pass"]
    assert "black_frames" in black["issues"] and not black["technical_pass"]
    assert "duration_mismatch" in wrong_duration["issues"]


def test_G_corrupt_download_is_qc_failure_not_success(tmp_path, settings):
    path = tmp_path / "not-video.mp4"
    path.write_bytes(b"invalid MP4 payload")
    report = inspect_video(path, settings, 6)
    assert not report["technical_pass"] and "probe_or_decode_error" in report["issues"]


def test_G_failed_shot_retry_is_bounded_and_resume_stable(tmp_path, settings, plan, media_factory):
    ledger = Ledger(tmp_path / "state.db", 10, True)
    provider = MockVideo()
    count = []
    def download(url, output):
        count.append(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media_factory(frozen=len(count) == 1), output)
    engine = VideoEngine(settings, ledger, AsyncJobs(ledger, downloader=download), {"runway": lambda: provider})
    first, _ = engine.generate(plan, plan.shots[0], plan.characters, None, tmp_path / "shot")
    assert provider.submissions == 2
    second, _ = engine.generate(plan, plan.shots[0], plan.characters, None, tmp_path / "shot")
    assert first == second and provider.submissions == 2
    assert ledger.summary()["reserved_ceiling_usd"] == 0.4
    ledger.close()


def test_decoded_duplicate_detection_survives_container_copy(settings, media_factory, tmp_path):
    first = media_factory()
    other = tmp_path / "renamed.mp4"
    shutil.copy2(first, other)
    different = media_factory(color=60)
    assert decoded_signature(first, settings) == decoded_signature(other, settings)
    assert decoded_signature(first, settings) != decoded_signature(different, settings)


@pytest.mark.parametrize("field,value", [("target_seconds", 10), ("shots", [])])
def test_incomplete_or_padded_episode_plan_rejected(plan, field, value):
    data = plan.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        Plan.model_validate(data)


def test_overlapping_dialogue_and_unknown_speaker_rejected(plan):
    data = plan.model_dump()
    data["shots"][0]["dialogue"] = [
        {"character": "actor_a", "text": "甲", "start": 0, "end": 1.2},
        {"character": "actor_a", "text": "乙", "start": 1.1, "end": 1.9}]
    with pytest.raises(ValidationError, match="overlapping"):
        Plan.model_validate(data)
    data["shots"][0]["dialogue"] = [{"character": "unknown", "text": "甲", "start": 0, "end": 1}]
    with pytest.raises(ValidationError, match="unknown speaker"):
        Plan.model_validate(data)


def test_budget_estimate_includes_whole_episode_retries_and_speech(settings, plan):
    plan.shots[0].dialogue = [Dialogue(character="actor_a", text="你好", start=0.5, end=1.5)]
    result = estimate(plan, settings)
    assert result["missing_rates"] == []
    assert result["all_attempts_and_configured_fallbacks_ceiling_usd"] == 0.83
    assert len([i for i in result["items"] if i["item"].startswith("character")]) == 3


def test_missing_costs_are_reported_without_inventing_prices(plan):
    from models import Settings
    result = estimate(plan, Settings())
    assert result["all_attempts_and_configured_fallbacks_ceiling_usd"] is None
    assert result["missing_rates"]


def test_reference_content_changes_video_cache_key(tmp_path, settings, plan):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"one")
    a = make_spec(plan, plan.shots[0], plan.characters, settings.video[0], frame)
    frame.write_bytes(b"two")
    b = make_spec(plan, plan.shots[0], plan.characters, settings.video[0], frame)
    assert content_key(a) != content_key(b)


def test_subtitle_overflow_and_ass_override_are_not_accepted(plan, tmp_path):
    with pytest.raises(CinemaError, match="two safe lines"):
        wrap_subtitle("中文" * 50, 20)
    plan.shots[0].dialogue = [Dialogue(character="actor_a", text=r"{\pos(999,999)}", start=0.1, end=1.8)]
    _, ass = subtitles(plan, tmp_path)
    assert r"\pos" not in ass.read_text(encoding="utf-8")


def test_capabilities_checked_without_credentials_or_network(plan, settings):
    result = validate_video_plan(plan, settings, require_keys=False)
    assert result[0]["usable"] == ["runway"]
    with pytest.raises(CinemaError, match="credentials"):
        validate_video_plan(plan, settings, require_keys=True)


def test_configured_provider_fallback_after_terminal_failure(tmp_path, settings, plan, media_factory):
    from models import VideoProviderConfig
    plan = plan.model_copy(deep=True)
    plan.shots[0].duration = 5
    plan.target_seconds = 5
    settings.video = [settings.video[0], VideoProviderConfig(name="kling", model="kling-v2-6")]
    first = MockVideo(states=["failed", "failed"])
    second = MockVideo()
    second.name = "kling"
    ledger = Ledger(tmp_path / "tasks.db", 10, True)
    def download(url, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media_factory(seconds=5), output)
    engine = VideoEngine(settings, ledger, AsyncJobs(ledger, downloader=download),
                         {"runway": lambda: first, "kling": lambda: second})
    _, report = engine.generate(plan, plan.shots[0], plan.characters, None, tmp_path / "shot")
    assert first.submissions == 2 and second.submissions == 1
    assert report["provider"] == "kling"
    assert ledger.summary()["reserved_ceiling_usd"] == 1.5
    ledger.close()


def test_production_pipeline_never_accepts_synthetic_provenance(tmp_path, settings, plan, media_factory, monkeypatch):
    import pipeline
    api = MockOpenAI()
    monkeypatch.setattr(pipeline, "check_environment", lambda p, s: estimate(p, s))
    monkeypatch.setattr(pipeline, "ImageEngine", lambda s, ledger: ImageEngine(s, ledger, api))
    def video_engine(s, ledger):
        def download(url, output):
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(media_factory(), output)
        return VideoEngine(s, ledger, AsyncJobs(ledger, downloader=download), {"runway": MockVideo})
    monkeypatch.setattr(pipeline, "VideoEngine", video_engine)
    with pytest.raises(CinemaError, match="Synthetic/mock footage"):
        pipeline.render_episode(plan, settings, tmp_path, 10, True)
    report = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert report["status"] == "incomplete"
    assert not (tmp_path / "episode_01.mp4").exists()
