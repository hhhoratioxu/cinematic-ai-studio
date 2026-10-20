from __future__ import annotations

import http.client
import json
import socket
import threading
from pathlib import Path

import pytest

from cinema import main
from common import BudgetError, CinemaError, digest, write_json
from models import Plan
from pipeline import render_episode
from project import (has_approval, quality_review, read_json, regenerate, render_from_assets,
                     review_asset, status, task_snapshot)
from state import Ledger
from studio import create_server, media_registry

REAL_CONNECT = socket.socket.connect


@pytest.fixture
def imported_project(tmp_path, plan, settings, media_factory):
    first = plan.shots[0].model_copy(update={"source_video": str(media_factory(color=0)),
        "source_license": "Synthetic moving test pattern for unit testing only"}, deep=True)
    second = first.model_copy(update={"id": "s002", "source_video": str(media_factory(color=80))}, deep=True)
    p = Plan.model_validate({**plan.model_dump(), "shots": [first.model_dump(), second.model_dump()],
                            "target_seconds": 4, "output": {"width": 160, "height": 288, "fps": 24,
                                                                  "burn_subtitles": False}})
    s = settings.model_copy(update={"max_shot_regenerations": 1})
    manifest = render_episode(p, s, tmp_path, 10, True)
    return tmp_path, p, s, manifest


def test_imported_dynamic_footage_exports_with_zero_model_calls_and_honest_levels(imported_project):
    directory, _, _, manifest = imported_project
    assert manifest["technical_qc"]["technical_pass"]
    assert task_snapshot(directory)["tasks"] == []
    assert task_snapshot(directory)["reserved_ceiling_usd"] == 0
    review = quality_review(directory, save=False)
    assert review["acceptance"]["Provider Live Verified"] == "Pending"
    assert review["acceptance"]["Full Episode Rendered"] == "Pending"
    assert review["acceptance"]["Editorially Reviewed"] == "Pending"


def test_local_reedit_does_not_construct_a_provider_or_ledger(imported_project, monkeypatch):
    directory, _, _, _ = imported_project
    def deny(*args, **kwargs):
        raise AssertionError("Free render must not construct paid execution machinery")
    monkeypatch.setattr("state.Ledger.__init__", deny)
    monkeypatch.setattr("providers.openai_api.OpenAI.__init__", deny)
    monkeypatch.setattr("providers.runway.Runway.__init__", deny)
    monkeypatch.setattr("providers.kling.Kling.__init__", deny)
    result = render_from_assets(directory)
    assert result["paid_calls_by_render"] == 0 and result["technical_qc"]["technical_pass"]


def test_review_is_bound_to_current_media_and_rejection_is_not_overridden(imported_project):
    directory, _, _, manifest = imported_project
    entry = manifest["shots"][0]
    with pytest.raises(CinemaError, match="stale"):
        review_asset(directory, "s001", "motion", "approve", "test reviewer", "Watched entire shot", "0" * 64)
    record = review_asset(directory, "s001", "motion", "approve", "test reviewer", "Watched test pattern", entry["source_sha256"])
    assert record["sha256"] == entry["source_sha256"]
    assert has_approval(directory, "s001", entry["source_sha256"], "motion")
    review_asset(directory, "s001", "editorial", "reject", "test reviewer", "Intentional test rejection", entry["source_sha256"])
    assert any("rejected" in item for item in quality_review(directory, save=False)["blocking"])
    with pytest.raises(CinemaError, match="Resolve"):
        review_asset(directory, "episode", "editorial", "approve", "test", "Watched", manifest["sha256"])


def test_bounded_regeneration_replaces_only_one_shot_and_retains_original(imported_project):
    directory, _, _, manifest = imported_project
    original = manifest["shots"][0]
    untouched = (directory / "shots/s002/accepted.json").read_bytes()
    result = regenerate(directory, "s001", 10, True, "Review prompted a local single-shot revision")
    assert result["revision"]["revision"] == 1
    assert Path(original["source_file"]).is_file()
    assert (directory / "shots/s002/accepted.json").read_bytes() == untouched
    revised = read_json(directory / "shots/s001/accepted.json")
    assert "revisions" in revised["source_file"]
    assert task_snapshot(directory)["reserved_ceiling_usd"] == 0
    with pytest.raises(CinemaError, match="limit"):
        regenerate(directory, "s001", 10, True, "Try beyond configured limit")


@pytest.mark.parametrize("authorized,budget", [(False, 10), (True, 11), (True, 0)])
def test_regeneration_requires_original_explicit_budget(imported_project, authorized, budget):
    directory, _, _, _ = imported_project
    with pytest.raises(BudgetError):
        regenerate(directory, "s001", budget, authorized, "test")


def test_unknown_charge_blocks_new_local_regeneration(imported_project):
    directory, _, _, _ = imported_project
    ledger = Ledger(directory / "tasks.sqlite3", 10, True)
    ledger.reserve("unknown", "runway", "video", 1, {}, directory / "unknown.mp4")
    ledger.update("unknown", state="uncertain")
    ledger.close()
    with pytest.raises(CinemaError, match="uncertain"):
        regenerate(directory, "s001", 10, True, "test")
    assert task_snapshot(directory)["reserved_ceiling_usd"] == 1


def test_changed_source_cannot_be_reedited_or_reviewed_as_intact(imported_project):
    directory, _, _, manifest = imported_project
    Path(manifest["shots"][0]["source_file"]).write_bytes(b"changed")
    assert any("changed" in b for b in quality_review(directory, save=False)["blocking"])
    with pytest.raises(CinemaError, match="changed"):
        render_from_assets(directory)


def test_readonly_status_and_cost_do_not_create_ledger_or_write_reports(tmp_path, plan, settings):
    write_json(tmp_path / "run.json", {"plan": plan.model_dump(), "settings": settings.model_dump(), "budget_usd": None})
    before = sorted(p.name for p in tmp_path.iterdir())
    assert status(tmp_path)["cost"]["tasks"] == []
    assert task_snapshot(tmp_path)["reserved_ceiling_usd"] == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_workbench_auth_origin_ranges_and_no_generation_endpoint(imported_project, monkeypatch):
    directory, _, _, manifest = imported_project
    def local_connect(sock, address):
        assert address[0] in ("127.0.0.1", "::1"), "No remote network is permitted"
        return REAL_CONNECT(sock, address)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    # http.client uses socket.create_connection; replace the test's global deny
    # with a loopback-only connector, keeping all external connections forbidden.
    def local_connection(address, timeout=None, source_address=None):
        assert address[0] == "127.0.0.1"
        sock = socket.socket()
        sock.settimeout(timeout)
        local_connect(sock, address)
        return sock
    monkeypatch.setattr(socket, "create_connection", local_connection)
    server = create_server(directory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request(method, path, payload, headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result
    try:
        auth = {"Authorization": "Bearer " + server.session_token}
        assert request("GET", "/api/state")[0] == 403
        assert request("GET", "/api/state", headers={**auth, "Host": "evil.test"})[0] == 403
        assert request("GET", "/api/state", headers={**auth, "Origin": "https://evil.test"})[0] == 403
        code, _, body = request("GET", "/api/state", headers=auth)
        assert code == 200 and json.loads(body)["title"] == manifest["title"]
        registry = media_registry(directory)
        key, file = next((k, p) for k, p in registry.items() if p.suffix == ".mp4")
        code, headers, body = request("GET", f"/media/{key}?token={server.session_token}", headers={"Range": "bytes=0-15"})
        assert code == 206 and body == file.read_bytes()[:16] and headers["Content-Length"] == "16"
        assert request("GET", f"/media/../../run.json?token={server.session_token}")[0] == 404
        entry = manifest["shots"][0]
        body = json.dumps({"target": "s001", "scope": "motion", "decision": "approve", "reviewer": "test",
                           "note": "Viewed motion evidence", "sha256": entry["source_sha256"]})
        assert request("POST", "/api/review", body, {**auth, "Content-Type": "application/json"})[0] == 403
        headers = {**auth, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
        assert request("POST", "/api/review", body, headers)[0] == 200
        assert request("POST", "/api/regenerate", "{}", headers)[0] == 404
        assert task_snapshot(directory)["tasks"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_media_registry_never_exposes_external_paths(imported_project, tmp_path):
    directory, _, _, _ = imported_project
    external = directory.parent / "outside.mp4"
    external.write_bytes(b"outside")
    write_json(directory / "shots/s001/accepted.json", {"source_file": str(external)})
    assert external.resolve() not in media_registry(directory).values()


def test_new_commands_help_and_v1_migration_are_available(tmp_path, plan):
    for name in ("studio", "render", "review", "status", "cost", "regenerate", "migrate"):
        with pytest.raises(SystemExit) as exc:
            main([name, "--help"])
        assert exc.value.code == 0
    source, output = tmp_path / "v1.json", tmp_path / "v2.json"
    write_json(source, plan.model_dump())
    original = digest(source)
    assert main(["migrate", "--plan", str(source), "--output", str(output)]) == 0
    assert digest(source) == original and read_json(output)["version"] == 2
