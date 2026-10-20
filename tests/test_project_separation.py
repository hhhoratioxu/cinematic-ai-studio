from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from cinema import main, parser
from common import CinemaError, atomic_bytes, write_json
from distribution_policy import ASSETS, approved, distribution_files
from fixtures import generic_plan
from install_skill import install
from state import Ledger
from workspace import SKILL_ROOT, ensure_external_project, new_project_directory


def test_new_projects_are_unique_external_and_not_created_by_a_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CINEMA_PROJECTS_DIR", str(tmp_path / "projects"))
    first, second = new_project_directory(), new_project_directory()
    assert first != second and first.parent == second.parent == tmp_path / "projects"
    assert not first.exists() and not second.exists()
    assert not first.is_relative_to(SKILL_ROOT)


@pytest.mark.parametrize("relative", ["projects/private/run.json", "assets/characters.json", "outputs/tasks.sqlite3"])
def test_production_writers_reject_repository_paths_before_creating_files(relative):
    target = SKILL_ROOT / relative
    with pytest.raises(CinemaError, match="outside"):
        atomic_bytes(target, b"private data must not enter the Skill")
    with pytest.raises(CinemaError, match="outside"):
        Ledger(target, 10, True)
    assert not target.exists()


def test_absolute_script_invocation_recognizes_another_skill_copy(tmp_path):
    other = tmp_path / "other-skill"
    (other / "scripts").mkdir(parents=True)
    (other / "SKILL.md").write_text("---\nname: cinematic-ai-studio\n---\n", encoding="utf-8")
    (other / "scripts/cinema.py").write_text("# generic skill marker\n", encoding="utf-8")
    with pytest.raises(CinemaError, match="every"):
        ensure_external_project(other / "my-private-project")
    assert ensure_external_project(tmp_path / "projects" / "my-film").is_relative_to(tmp_path / "projects")


def test_story_runtime_is_explicit_and_missing_story_never_loads_a_fixture(tmp_path):
    assert parser().parse_args(["episode", "--story-file", "external-story.txt"]).seconds is None
    with pytest.raises(CinemaError, match="explicit --seconds"):
        main(["episode", "--story-file", str(tmp_path / "input.txt"), "--out", str(tmp_path / "render")])
    with pytest.raises(CinemaError, match="Use --plan"):
        main(["episode", "--out", str(tmp_path / "other")])
    assert not list(tmp_path.rglob("*.sqlite3"))
    assert not (tmp_path / "render").exists()


def test_generic_plan_is_written_only_to_a_new_external_workspace(tmp_path, capsys):
    plan_file = tmp_path / "input.plan.json"
    write_json(plan_file, generic_plan(6).model_dump())
    project = tmp_path / "productions" / "fresh"
    assert main(["plan", "--plan", str(plan_file), "--out", str(project)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["project_directory"] == str(project.resolve())
    assert (project / "shot_plan.json").is_file() and (project / "director_plan.json").is_file()
    assert not (project / "tasks.sqlite3").exists()
    before = (project / "shot_plan.json").read_bytes()
    with pytest.raises(CinemaError, match="already exists"):
        main(["plan", "--plan", str(plan_file), "--out", str(project)])
    assert (project / "shot_plan.json").read_bytes() == before


def test_gitignore_covers_private_inputs_and_records_but_keeps_generic_sources():
    ignored = ["projects/production/user-notes.txt", "private/input.txt", "inputs/user.plan.json", "story.txt",
        "characters.json", "shot_plan.json", "scene_bible.json", "run.json", "cost_report.json", "tasks.sqlite3",
        ".env", ".env.local", "credentials.json", "reference.png", "source.mp4", "dialogue.wav", "revisions.json"]
    result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin", "-z"], cwd=SKILL_ROOT,
        input=("\0".join(ignored) + "\0").encode(), capture_output=True)
    assert set(result.stdout.decode().strip("\0").split("\0")) == set(ignored)
    public = ["scripts/cinema.py", "tests/fixtures.py", "assets/config.example.json", "assets/characters.example.json", "SKILL.md"]
    result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin", "-z"], cwd=SKILL_ROOT,
        input=("\0".join(public) + "\0").encode(), capture_output=True)
    assert not result.stdout


def test_package_allowlist_rejects_an_ignored_private_asset_before_installing(tmp_path, monkeypatch):
    import install_skill
    source = install(tmp_path / "generic-source")
    private = source / "assets" / "private.plan.json"
    private.write_text('{"private": true}', encoding="utf-8")
    monkeypatch.setattr(install_skill, "ROOT", source)
    with pytest.raises(ValueError, match="Unapproved"):
        install(tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_generic_zip_contains_only_allowlisted_files_and_no_project_data(tmp_path, monkeypatch):
    import package_skill
    source = install(tmp_path / "generic-source")
    monkeypatch.setattr(package_skill, "ROOT", source)
    report = package_skill.package(tmp_path / "release")
    with zipfile.ZipFile(tmp_path / "release" / report["archive"]) as archive:
        names = [Path(n.removeprefix("cinematic-ai-studio/")) for n in archive.namelist()]
        assert all(approved(p) for p in names)
        assert {p.name for p in names if p.parts[0] == "assets"} == ASSETS
        assert not any(p.suffix in (".mp4", ".wav", ".sqlite3") or p.name.endswith(".plan.json") for p in names)
        assert len(names) == len(distribution_files(source))
        assert not archive.testzip()


def test_distribution_rejects_a_forced_tracked_private_file(tmp_path):
    from distribution_policy import audit_tracked
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "private.plan.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "private.plan.json"], check=True)
    with pytest.raises(ValueError, match="Unapproved tracked"):
        audit_tracked(tmp_path)
