from __future__ import annotations


import pytest

from audio_engine import AudioEngine
from common import digest, write_json
from install_skill import install
from mock_provider import MockOpenAI, MockVideo
from models import Dialogue
from providers.base import AsyncJobs
from state import Ledger
from video_engine import VideoEngine


def test_managed_upgrade_preserves_a_verified_backup_and_rejects_user_edits(tmp_path):
    dest = install(tmp_path / "agents/skills/cinematic-ai-studio")
    before = (dest / "SKILL.md").read_bytes()
    assert install(dest, upgrade=True) == dest
    backups = list((tmp_path / "agents/skill-backups").glob("cinematic-ai-studio-*"))
    assert len(backups) == 1 and (backups[0] / "SKILL.md").read_bytes() == before
    (dest / "local-note.txt").write_text("User customization", encoding="utf-8")
    with pytest.raises(ValueError, match="user-modified"):
        install(dest, upgrade=True)
    assert (dest / "local-note.txt").read_text(encoding="utf-8") == "User customization"


def test_matching_tts_is_reused_across_revision_directories_without_repurchase(tmp_path, settings, plan):
    plan.shots[0].dialogue = [Dialogue(character="actor_a", text="这是测试", start=0.1, end=1.8)]
    plan.characters[0].speech_style = "Restrained, short breaths and thoughtful pauses"
    plan.characters[0].speech_speed = 0.95
    api = MockOpenAI()
    ledger = Ledger(tmp_path / "tasks.sqlite3", 10, True)
    first, _ = AudioEngine(settings, ledger, api).dialogue(plan.shots[0], plan.characters, tmp_path / "first")
    second, _ = AudioEngine(settings, ledger, api).dialogue(plan.shots[0], plan.characters, tmp_path / "revision")
    assert first.is_file() and second.is_file() and digest(first) == digest(second)
    assert len(api.calls) == 1
    assert "0.95" in api.calls[0]["instructions"] and "Restrained" in api.calls[0]["instructions"]
    ledger.close()


def test_revision_creates_one_new_video_job_and_resume_reuses_same_job(tmp_path, settings, plan, media_factory):
    import shutil
    ledger = Ledger(tmp_path / "tasks.sqlite3", 10, True)
    provider = MockVideo()
    def download(url, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media_factory(), output)
    engine = VideoEngine(settings, ledger, AsyncJobs(ledger, downloader=download), {"runway": lambda: provider})
    original, _ = engine.generate(plan, plan.shots[0], plan.characters, None, tmp_path / "original")
    revised, _ = engine.generate(plan, plan.shots[0], plan.characters, None, tmp_path / "revision", revision=1)
    resumed, _ = engine.generate(plan, plan.shots[0], plan.characters, None, tmp_path / "revision", revision=1)
    assert provider.submissions == 2 and revised == resumed and original != revised
    assert provider.specs[-1]["generation_revision"] == "s001:1"
    assert ledger.summary()["reserved_ceiling_usd"] == 0.4
    ledger.close()


def test_overlapping_music_cues_and_sound_fades_render_locally(tmp_path, plan, settings):
    from models import MusicCue
    from pipeline import music_bus
    from quality_control import probe
    plan = plan.model_copy(update={"target_seconds": 4, "shots": [plan.shots[0].model_copy(update={"duration": 4})]})
    plan.music_cues = [MusicCue(id="first", start=0, end=3, fade_in=0.2, fade_out=1),
                       MusicCue(id="second", start=2, end=4, fade_in=1, fade_out=0.2)]
    file = music_bus(plan, settings, tmp_path)
    assert file.is_file() and abs(probe(file, settings)["duration"] - 4) < 0.05
    assert not (tmp_path / "tasks.sqlite3").exists()


def test_interrupted_revision_uses_saved_override_instead_of_changing_request(tmp_path, plan, settings, monkeypatch):
    import project
    replacement = plan.shots[0].model_copy(update={"expression": "visible hesitation"}, deep=True)
    from models import Shot
    replacement = Shot.model_validate(replacement.model_dump())
    from common import CinemaError, content_key
    write_json(tmp_path / "run.json", {"plan": plan.model_dump(), "settings": settings.model_dump(), "budget_usd": 10})
    write_json(tmp_path / "revisions.json", [{"shot": replacement.id, "revision": 1, "state": "in_progress",
        "note": "test saved override", "spec_sha256": content_key(replacement.model_dump()), "shot_spec": replacement.model_dump()}])
    monkeypatch.setattr("pipeline.check_environment", lambda *args: {})
    seen = []
    def process(p, shot, *args, **kwargs):
        seen.append(shot)
        raise CinemaError("Simulated known in-progress task, no new submission")
    monkeypatch.setattr("pipeline.process_shot", process)
    with pytest.raises(CinemaError, match="in-progress"):
        project.regenerate(tmp_path, replacement.id, 10, True, "resume saved override")
    assert seen[0].expression == replacement.expression
    assert len(project.read_json(tmp_path / "revisions.json")) == 1


def test_unmanaged_legacy_upgrade_uses_an_opaque_tree_fingerprint(tmp_path, monkeypatch):
    import json
    import install_skill
    from common import content_key
    source = install(tmp_path / "source")
    legacy = install(tmp_path / "skills/legacy")
    (legacy / ".install-manifest.json").unlink()
    expected = content_key(install_skill.file_hashes(legacy))
    (source / "assets/legacy-install-fingerprints.json").write_text(json.dumps({"test-legacy": expected}), encoding="utf-8")
    monkeypatch.setattr(install_skill, "ROOT", source)
    assert install(legacy, upgrade=True) == legacy
    backups = list((tmp_path / "skill-backups").glob("legacy-*"))
    assert len(backups) == 1 and content_key(install_skill.file_hashes(backups[0])) == expected
