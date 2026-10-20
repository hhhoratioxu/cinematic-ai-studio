"""Project status, hash-bound review, free re-editing, and bounded single-shot replacement."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from common import BudgetError, CinemaError, content_key, digest, write_json
from models import Plan, Settings, Shot


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def task_snapshot(directory):
    path = directory / "tasks.sqlite3"
    if not path.is_file():
        return {"budget_usd": None, "reserved_ceiling_usd": 0, "actual_billed_usd": None, "tasks": []}
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute("SELECT key,provider,kind,ceiling,state,task_id,output,sha256,error FROM tasks ORDER BY created,key")]
        budget = db.execute("SELECT value FROM meta WHERE key='budget'").fetchone()
    reserved = sum(row["ceiling"] for row in rows) / 1e6
    for row in rows:
        row["reserved_ceiling_usd"] = row.pop("ceiling") / 1e6
    return {"budget_usd": int(budget[0]) / 1e6 if budget else None, "reserved_ceiling_usd": reserved,
            "actual_billed_usd": None, "tasks": rows,
            "billing_note": "Reviewed upper-bound reservations, including failed/unknown tasks; invoice not measured"}


def project_plan(directory):
    saved = read_json(directory / "run.json", {})
    raw = read_json(directory / "shot_plan.json", saved.get("plan"))
    if raw is None:
        raise CinemaError("Project has no saved plan; use plan --plan ... --out ... first")
    return Plan.model_validate(raw), Settings.model_validate(saved.get("settings", {})), saved


def accepted_shots(directory, plan):
    return {s.id: read_json(directory / "shots" / s.id / "accepted.json", {}) for s in plan.shots}


def has_approval(directory, target, sha256, scope):
    records = read_json(directory / "reviews.json", [])
    records = [r for r in records if (r["target"], r["sha256"], r["scope"]) == (target, sha256, scope)]
    return bool(records and records[-1]["decision"] == "approve")


def review_asset(directory, target, scope, decision, reviewer, note, expected_sha256, raw=False):
    plan, _, _ = project_plan(directory)
    if scope not in ("motion", "editorial") or decision not in ("approve", "reject"):
        raise CinemaError("Review scope must be motion/editorial and decision approve/reject")
    if not reviewer.strip() or not note.strip():
        raise CinemaError("A reviewer and observation note are required")
    if target == "episode":
        manifest = read_json(directory / "manifest.json", {})
        path = Path(manifest.get("output", "__missing__"))
        if not manifest.get("technical_qc", {}).get("technical_pass"):
            raise CinemaError("Episode must pass technical QC before editorial approval")
    else:
        if target not in {s.id for s in plan.shots}:
            raise CinemaError("Unknown shot")
        accepted = read_json(directory / "shots" / target / "accepted.json", {})
        candidates = [Path(accepted.get("generated_file" if raw else "source_file", "__missing__"))]
        if raw:
            root = (directory / "shots" / target).resolve()
            # An interrupted pre-lipsync shot may not have an accepted.json yet.
            candidates += [Path(t["output"]) for t in task_snapshot(directory)["tasks"]
                           if t["kind"] == "video" and t["state"] == "complete" and
                           Path(t["output"]).resolve().is_relative_to(root)]
        path = next((p for p in candidates if p.is_file() and digest(p) == expected_sha256), candidates[0])
    if not path.is_file() or digest(path) != expected_sha256:
        raise CinemaError("Review hash is stale or asset is unavailable; inspect the current asset")
    if decision == "approve" and target == "episode":
        report = quality_review(directory, save=False)
        if report["blocking"] or report["motion_review_pending"]:
            raise CinemaError("Resolve missing/rejected/changed shots and pending motion reviews before final approval")
    record = {"target": target, "scope": scope, "decision": decision, "reviewer": reviewer.strip(),
              "note": note.strip(), "sha256": expected_sha256, "file": str(path),
              "time": datetime.now(timezone.utc).isoformat()}
    records = read_json(directory / "reviews.json", [])
    records.append(record)
    write_json(directory / "reviews.json", records)
    quality_review(directory)
    return record


def quality_review(directory, manifest=None, save=True):
    from continuity_engine import continuity_report
    plan, _, _ = project_plan(directory)
    manifest = manifest or read_json(directory / "manifest.json", {})
    entries = accepted_shots(directory, plan)
    blocking, motion_pending, shots = [], [], []
    signatures = []
    for shot in plan.shots:
        entry = entries[shot.id]
        if not entry:
            blocking.append(f"{shot.id}: missing accepted source")
            shots.append({"id": shot.id, "status": "missing"})
            continue
        source = Path(entry["source_file"])
        expected = entry["source_sha256"]
        intact = source.is_file() and digest(source) == expected
        qc = entry.get("lipsync", {}).get("qc", entry.get("qc", {}))
        if not intact or not qc.get("technical_pass"):
            blocking.append(f"{shot.id}: source changed or technical QC failed")
        if entry.get("evidence") not in ("real_api_video", "user_supplied_dynamic_video"):
            blocking.append(f"{shot.id}: test/synthetic provenance cannot enter production")
        signatures.append(entry.get("decoded_signature"))
        flags = qc.get("motion", {}).get("status", "needs_review")
        approved = has_approval(directory, shot.id, expected, "motion")
        if flags == "needs_review" and not approved:
            motion_pending.append(shot.id)
        rejected = any(r["decision"] == "reject" and not has_approval(directory, shot.id, expected, r["scope"])
                       for r in read_json(directory / "reviews.json", [])
                       if r["target"] == shot.id and r["sha256"] == expected)
        if rejected:
            blocking.append(f"{shot.id}: rejected by reviewer")
        shots.append({"id": shot.id, "sha256": expected, "intact": intact,
                      "technical_pass": qc.get("technical_pass", False), "motion": qc.get("motion"),
                      "motion_approved": approved, "semantic_quality": "requires audiovisual review"})
    if len([s for s in signatures if s]) != len(set(s for s in signatures if s)):
        blocking.append("duplicate decoded shots")
    continuity = continuity_report(plan)
    blocking.extend(continuity["errors"])
    final = Path(manifest.get("output", "__missing__"))
    final_intact = bool(final.is_file() and manifest.get("sha256") == digest(final))
    if manifest.get("output") and not final_intact:
        blocking.append("episode changed/missing since QC")
    editorial = bool(final_intact and has_approval(directory, "episode", manifest["sha256"], "editorial") and not blocking and not motion_pending)
    all_generated = all(e.get("evidence") == "real_api_video" for e in entries.values())
    live_proof = all_generated and final_intact and not blocking and bool(manifest.get("technical_qc", {}).get("technical_pass"))
    report = {"status": "blocked" if blocking else "editorially_reviewed" if editorial else "needs_review",
              "blocking": blocking, "motion_review_pending": motion_pending, "shots": shots,
              "continuity": continuity, "final_sha256": manifest.get("sha256"),
              "acceptance": {"Offline Tested": "See release validation; not asserted for this project",
                             "Media Pipeline Verified": "Passed for this output" if final_intact and manifest.get("technical_qc", {}).get("technical_pass") else "Pending",
                             "Provider Live Verified": "Recorded generated sources" if live_proof else "Pending",
                             "Full Episode Rendered": "Rendered; editorial review pending" if live_proof else "Pending",
                             "Editorially Reviewed": "Approved by recorded reviewer" if editorial else "Pending"},
              "technical_checks_do_not_certify": ["identity", "acting", "anatomy", "lip synchronization", "cinematic quality"]}
    if save:
        write_json(directory / "quality_review.json", report)
    return report


def status(directory):
    plan, settings, saved = project_plan(directory)
    return {"title": plan.title, "version": "0.5.0", "mode": plan.mode,
            "plan": plan.model_dump(), "configured_models": [c.model_dump() for c in settings.video],
            "manifest": read_json(directory / "manifest.json", {}), "cost": task_snapshot(directory),
            "accepted": [e for e in accepted_shots(directory, plan).values() if e],
            "review": quality_review(directory, save=False), "revisions": read_json(directory / "revisions.json", []),
            "test_only": saved.get("test_only", False), "paid_calls_by_this_command": 0}


def render_from_assets(directory, plan_file=None):
    """No API client or Ledger construction: safely repair formats/re-edit existing material."""
    from audio_engine import subtitles
    from editing_engine import export_episode, normalize_shot
    from fonts import select_font
    from pipeline import music_bus
    from quality_control import inspect_episode, inspect_video, require_pass
    from storyboard_engine import resolve_plan_assets
    plan, settings, saved = project_plan(directory)
    if saved.get("test_only"):
        raise CinemaError("Test fixtures cannot be relabeled as production")
    if plan_file:
        edit = resolve_plan_assets(Plan.model_validate(read_json(plan_file)), plan_file.resolve().parent)
        # Editing may reorder existing complete shots, change grade/format/music/subtitle display.
        if {s.id for s in edit.shots} != {s.id for s in plan.shots}:
            raise CinemaError("Free re-edit must preserve the set of accepted shot IDs")
        old = {s.id: s for s in plan.shots}
        for shot in edit.shots:
            if shot.duration != old[shot.id].duration or shot.dialogue != old[shot.id].dialogue:
                raise CinemaError("Changing duration/dialogue requires an explicit shot revision")
        plan = edit
    from continuity_engine import require_continuity
    require_continuity(plan)
    plan = plan.model_copy(update={"output": select_font(plan.output, needed=plan.output.burn_subtitles and any(s.dialogue for s in plan.shots))})
    entries = accepted_shots(directory, plan)
    clips, timings, signatures = [], {}, []
    for shot in plan.shots:
        e = entries[shot.id]
        if e.get("evidence") not in ("real_api_video", "user_supplied_dynamic_video"):
            raise CinemaError(f"{shot.id}: missing or synthetic source")
        source, audio = Path(e["source_file"]), Path(e["mixed_audio"])
        if digest(source) != e["source_sha256"] or digest(audio) != e["mixed_audio_sha256"]:
            raise CinemaError(f"{shot.id}: source/audio changed; restore or revise that shot")
        qc = inspect_video(source, settings, duration=shot.duration, shot=shot)
        require_pass(qc, shot.id)
        signatures.append(e["decoded_signature"])
        clip = directory / "reedit" / f"{shot.id}.mkv"
        e["postprocessing"] = normalize_shot(source, audio, clip, shot, plan.output, settings)
        clips.append(clip)
        timings[shot.id] = e.get("dialogue_timing", [])
    if len(signatures) != len(set(signatures)):
        raise CinemaError("Duplicate decoded shot content")
    edit_dir = directory / "edit"
    edit_dir.mkdir(exist_ok=True)
    srt, _ = subtitles(plan, edit_dir, timings)
    final = export_episode(clips, plan, edit_dir, settings, music_bus(plan, settings, directory))
    qc = inspect_episode(final, plan, settings)
    require_pass(qc, "episode")
    result = {"version": 2, "status": "rendered_requires_editorial_review", "test_only": False,
              "title": plan.title, "episode": plan.episode, "mode": plan.mode, "target_seconds": plan.target_seconds,
              "output": str(final), "sha256": digest(final), "technical_qc": qc,
              "shots": list(entries.values()), "subtitles": str(srt), "cost": task_snapshot(directory),
              "paid_calls_by_render": 0, "disclosure": "Generated or user-supplied sources; inspect each shot's provenance"}
    write_json(directory / "shot_plan.json", plan.model_dump())
    from director_engine import production_packet
    production_packet(plan, directory)
    write_json(directory / "manifest.json", result)
    write_json(directory / "qc_report.json", qc)
    quality_review(directory, result)
    return result


def regenerate(directory, shot_id, budget, authorized, note, shot_file=None, rerender=False):
    from pipeline import check_environment, process_shot
    from state import Ledger
    plan, settings, saved = project_plan(directory)
    if not authorized or budget is None or budget != saved.get("budget_usd") or budget <= 0:
        raise BudgetError("Single-shot regeneration requires --allow-paid with the original positive --budget-usd")
    if saved.get("test_only") or not note.strip():
        raise CinemaError("Use a production project and provide a regeneration reason")
    shot = next((s for s in plan.shots if s.id == shot_id), None)
    if not shot:
        raise CinemaError("Unknown shot ID")
    replacement = Shot.model_validate(read_json(shot_file)) if shot_file else shot
    # Normalize default numeric values exactly as they will be read from saved JSON.
    replacement = Shot.model_validate(replacement.model_dump())
    if replacement.id != shot_id or replacement.duration != shot.duration:
        raise CinemaError("A local revision must retain the shot ID and duration")
    updated = Plan.model_validate({**plan.model_dump(), "shots": [replacement.model_dump() if s.id == shot_id else s.model_dump() for s in plan.shots]})
    # Any unresolved charge blocks a new paid revision, even if it belongs to another shot.
    pending = [t for t in task_snapshot(directory)["tasks"] if t["state"] in ("submitting", "uncertain", "submitted")]
    revisions = read_json(directory / "revisions.json", [])
    own = [r for r in revisions if r["shot"] == shot_id]
    active = next((r for r in reversed(own) if r["state"] == "in_progress"), None)
    fingerprint = content_key(replacement.model_dump())
    if active:
        if not shot_file and active.get("shot_spec"):
            replacement = Shot.model_validate(active["shot_spec"])
            fingerprint = content_key(replacement.model_dump())
            updated = Plan.model_validate({**plan.model_dump(), "shots": [replacement.model_dump() if s.id == shot_id else s.model_dump() for s in plan.shots]})
        if active["spec_sha256"] != fingerprint:
            raise CinemaError("An unfinished revision must be resumed with the same shot specification")
        if any(t["state"] in ("submitting", "uncertain") for t in pending):
            raise CinemaError("Reconcile uncertain submissions before resuming this revision")
    else:
        if pending:
            raise CinemaError("Resolve existing submitted/uncertain tasks before authorizing a new revision")
        if len(own) >= settings.max_shot_regenerations:
            raise CinemaError("Single-shot regeneration limit reached; no automatic budget/limit increase")
        active = {"shot": shot_id, "revision": len(own) + 1, "note": note,
                  "state": "in_progress", "spec_sha256": fingerprint, "shot_spec": replacement.model_dump()}
        revisions.append(active)
        write_json(directory / "revisions.json", revisions)
    # Preflight only this shot. Other shots never go through a generation engine.
    single = updated.model_copy(update={"shots": [replacement], "target_seconds": replacement.duration,
                                        "music_file": None, "music_cues": []})
    check_environment(single, settings)
    ledger = Ledger(directory / "tasks.sqlite3", budget, True)
    try:
        _, entry, _ = process_shot(updated, replacement, settings, ledger, directory, revision=active["revision"])
        if entry.get("evidence") not in ("real_api_video", "user_supplied_dynamic_video"):
            raise CinemaError("Synthetic/mock footage cannot replace a production shot")
        write_json(directory / "shots" / shot_id / "accepted.json", entry)
        write_json(directory / "shot_plan.json", updated.model_dump())
        active["state"] = "complete"
        active["source_sha256"] = entry["source_sha256"]
        write_json(directory / "revisions.json", revisions)
    finally:
        write_json(directory / "cost_report.json", ledger.summary())
        ledger.close()
    quality_review(directory)
    if rerender:
        return render_from_assets(directory)
    return {"shot": shot_id, "revision": active, "cost": task_snapshot(directory), "next": "render --out PROJECT (zero paid calls)"}
