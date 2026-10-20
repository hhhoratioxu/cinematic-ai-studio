#!/usr/bin/env python3
"""Cinematic AI Studio. Running help, doctor, estimate, inspect never buys generation."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str), flush=True)


def parser():
    p = argparse.ArgumentParser(description="Real AI video production for Codex. No paid generation by default.")
    p.add_argument("--version", action="version", version="cinematic-ai-studio 0.1.0")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Offline dependency, media tool, and credential-presence checks")
    sub.add_parser("providers", help="Verified provider capabilities and documentation links")
    schema = sub.add_parser("schema", help="Print the canonical plan or character JSON Schema")
    schema.add_argument("kind", choices=["plan", "character"], default="plan", nargs="?")
    for name in ("episode", "shot", "estimate", "plan"):
        q = sub.add_parser(name)
        q.add_argument("--plan", type=Path)
        q.add_argument("--story-file", type=Path)
        q.add_argument("--seconds", type=int, default=180)
        q.add_argument("--mode", choices=["live_action", "anime", "motion_comic", "ai_drama"], default="ai_drama")
        q.add_argument("--bible", type=Path, help="Reuse a persistent characters.json across episodes")
        if name == "shot":
            q.add_argument("--shot-id", required=True)
        generation_args(q)
    image = sub.add_parser("image")
    image.add_argument("--prompt", required=True)
    image.add_argument("--reference", type=Path, action="append", default=[])
    image.add_argument("--filename", default="image.png")
    generation_args(image)
    char = sub.add_parser("character", help="Validate/list a bible, or generate missing reference views")
    char.add_argument("--bible", type=Path, required=True)
    char.add_argument("--generate", action="store_true")
    char.add_argument("--style", default="original cinematic live action")
    generation_args(char)
    resume = sub.add_parser("resume")
    resume.add_argument("--out", type=Path, required=True)
    resume.add_argument("--allow-paid", action="store_true")
    resume.add_argument("--budget-usd", type=float, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("file", type=Path)
    inspect.add_argument("--plan", type=Path)
    inspect.add_argument("--config", type=Path)
    inspect.add_argument("--report", type=Path)
    resolve = sub.add_parser("reconcile", help="Attach a confirmed existing task/result; never creates a task")
    resolve.add_argument("--out", type=Path, required=True)
    resolve.add_argument("--task-key", required=True)
    resolve.add_argument("--task-id")
    resolve.add_argument("--import-file", type=Path)
    resolve.add_argument("--note", required=True, help="Evidence used to reconcile the existing paid action")
    return p


def generation_args(q):
    q.add_argument("--config", type=Path)
    q.add_argument("--out", type=Path, default=Path("output/cinematic-studio"))
    q.add_argument("--budget-usd", type=float)
    q.add_argument("--allow-paid", action="store_true", help="Explicitly authorize paid actions up to the given budget")


def doctor():
    import platform
    dependencies = {m: importlib.util.find_spec(m) is not None for m in ("httpx", "pydantic", "PIL", "yaml")}
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        from common import CinemaError, media_tool
        try:
            candidate = media_tool(name)
            tools[name] = {"path": candidate, "available": True}
        except CinemaError:
            tools[name] = {"path": None, "available": False}
    keys = {name: bool(os.environ.get(name)) for name in
            ("OPENAI_API_KEY", "RUNWAYML_API_SECRET", "KLING_API_KEY", "KLING_ACCESS_KEY", "KLING_SECRET_KEY",
             "SYNC_API_KEY")}
    capabilities = None
    if tools["ffmpeg"]["available"]:
        from common import media_capabilities
        capabilities = media_capabilities()
    report = {"python": platform.python_version(), "python_supported": sys.version_info >= (3, 11),
              "platform": platform.platform(), "dependencies": dependencies, "media_tools": tools,
              "credential_presence_only": keys, "network_or_model_access_tested": False,
              "paid_calls": 0, "media_capabilities": capabilities,
              "note": "Keys are checked for presence only. No generation is requested."}
    emit(report)
    full_media = capabilities and not capabilities["missing_filters"] and not capabilities["missing_encoders"]
    return 0 if all(dependencies.values()) and all(t["available"] for t in tools.values()) and full_media else 2


def providers():
    emit({"checked": "2026-10-20", "adapters": [
        {"provider": "OpenAI", "capabilities": ["text_to_image", "reference_image_edit", "Mandarin_TTS",
                                                 "story_planning", "probabilistic_vision_QC"],
         "docs": "https://developers.openai.com/api/docs/guides/image-generation"},
        {"provider": "Runway", "models": ["gen4.5", "gen4_turbo", "veo3.1", "veo3.1_fast"],
         "capabilities": ["text_to_video (except Turbo)", "image_to_video", "async_tasks", "sound_effects"],
         "last_frame": "veo3.1 / veo3.1_fast only", "docs": "https://docs.dev.runwayml.com/api/"},
        {"provider": "Kling", "models": ["kling-v2-6", "kling-v3"], "api": "official supported legacy API",
         "capabilities": ["text_to_video", "image_to_video", "first_last_frame", "async_tasks"],
         "elements": "existing library IDs, Kling 3 image-to-video only",
         "docs": "https://kling.ai/document-api/api/video/2-6/image-to-video/legacy"},
        {"provider": "Sync", "models": ["lipsync-2", "lipsync-2-pro"],
         "capabilities": ["lip_sync_existing_dynamic_video_to_timed_audio", "async_tasks"],
         "docs": "https://sync.so/docs/api-reference/api/generate-api/create-with-files"}],
         "real_generation_acceptance": "Requires authorized paid E2E; offline tests do not establish model quality"})


def configured(path):
    from models import Settings, read_model
    return read_model(path, Settings) if path else Settings()


def paid_guard(args):
    from common import BudgetError
    if args.allow_paid and (args.budget_usd is None or not 0 < args.budget_usd < float("inf")):
        raise BudgetError("--allow-paid requires a positive finite --budget-usd")


def load_plan(args, settings):
    from character_engine import merge_bible
    from models import Character, Plan, read_model
    from storyboard_engine import resolve_plan_assets
    if not args.plan:
        from common import CinemaError
        raise CinemaError("Use --plan for an existing Codex-authored plan, or --story-file with paid planning")
    plan = resolve_plan_assets(read_model(args.plan, Plan), args.plan.resolve().parent)
    if args.bible:
        bible = [Character.model_validate(c) for c in json.loads(args.bible.read_text(encoding="utf-8-sig"))]
        for c in bible:
            c.references = {k: str((args.bible.resolve().parent / v).resolve())
                            for k, v in c.references.items()}
        plan = merge_bible(plan, bible)
    if args.command == "shot":
        from common import CinemaError
        shots = [s for s in plan.shots if s.id == args.shot_id]
        if not shots:
            raise CinemaError(f"Unknown shot ID {args.shot_id}")
        plan = plan.model_copy(update={"shots": shots, "target_seconds": shots[0].duration})
    return plan


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "providers":
        providers()
        return 0
    from common import CinemaError, content_key, write_json
    from models import Character, Plan, Settings, read_model
    from state import Ledger, run_lock
    if args.command == "schema":
        emit((Plan if args.kind == "plan" else Character).model_json_schema())
        return 0
    if args.command == "inspect":
        from quality_control import inspect_video
        settings = configured(args.config)
        plan = read_model(args.plan, Plan) if args.plan else None
        report = inspect_video(args.file, settings, plan.target_seconds if plan else None,
                               plan.output if plan else None, require_audio=bool(plan))
        if args.report:
            write_json(args.report, report)
        emit(report)
        return 0 if report["technical_pass"] else 2
    if args.command == "reconcile":
        saved = json.loads((args.out / "run.json").read_text(encoding="utf-8"))
        if bool(args.task_id) == bool(args.import_file):
            raise CinemaError("Choose exactly one of --task-id or --import-file")
        with run_lock(args.out):
            ledger = Ledger(args.out / "tasks.sqlite3", saved["budget_usd"], False)
            try:
                row = ledger.get(args.task_key)
                if not row or row["state"] not in ("uncertain", "submitting", "complete"):
                    raise CinemaError("Reconcile requires an existing uncertain/submitting or lost complete task")
                metadata = {"manual_reconciliation_note": args.note}
                if args.task_id:
                    if row["kind"] not in ("video", "sfx", "lipsync"):
                        raise CinemaError("Synchronous APIs cannot be recovered with an asynchronous task ID")
                    if not __import__("re").fullmatch(r"[A-Za-z0-9_-]{1,128}", args.task_id):
                        raise CinemaError("Invalid task ID")
                    ledger.update(args.task_key, state="submitted", task_id=args.task_id,
                                  metadata=json.dumps(metadata), error=None)
                else:
                    from shutil import copy2
                    destination = Path(row["output"])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    copy2(args.import_file, destination)
                    ledger.complete(args.task_key, destination, metadata)
                emit({"reconciled": args.task_key, "paid_calls": 0, "cost": ledger.summary()})
            finally:
                ledger.close()
        return 0
    if args.command == "resume":
        paid_guard(args)
        saved = json.loads((args.out / "run.json").read_text(encoding="utf-8"))
        if saved.get("test_only"):
            raise CinemaError("Test fixtures cannot be resumed as production")
        if not args.allow_paid:
            raise CinemaError("Resume may create unfinished assets; pass --allow-paid with original budget")
        from pipeline import render_episode
        with run_lock(args.out):
            result = render_episode(Plan.model_validate(saved["plan"]), Settings.model_validate(saved["settings"]),
                                    args.out, args.budget_usd, True, event=emit)
        emit({k: result[k] for k in ("status", "output", "sha256", "cost")})
        return 0
    settings = configured(args.config)
    paid_guard(args)
    if args.command in ("episode", "shot", "plan", "estimate"):
        from pipeline import estimate, render_episode
        if args.story_file:
            if args.plan:
                raise CinemaError("Choose either --plan or --story-file")
            from image_engine import rate
            ceiling = rate(settings, "openai:planner")
            emit({"stage": "planning_estimate", "ceiling_usd": ceiling,
                  "note": "Episode cost estimate follows planning and precedes any image/video purchase"})
            if not args.allow_paid or args.command == "estimate":
                return 0
            from storyboard_engine import plan_story
            with run_lock(args.out):
                ledger = Ledger(args.out / "tasks.sqlite3", args.budget_usd, True)
                try:
                    write_json(args.out / "run.json", {"budget_usd": args.budget_usd,
                        "settings": settings.model_dump(), "command": "story_planning", "test_only": False})
                    ledger.bind("story_inputs", content_key({"story": args.story_file.read_text(encoding="utf-8-sig"),
                                "seconds": args.seconds, "mode": args.mode, "settings": settings.model_dump()}))
                    output = args.out / "planned_story.json"
                    plan = plan_story(args.story_file.read_text(encoding="utf-8-sig"), args.seconds, args.mode,
                                      settings, ledger, output)
                    write_json(args.out / "run.json", {"plan": plan.model_dump(), "settings": settings.model_dump(),
                                                       "budget_usd": args.budget_usd, "test_only": False})
                    report = estimate(plan, settings)
                    emit(report)
                    if args.command == "plan":
                        return 0
                    result = render_episode(plan, settings, args.out, args.budget_usd, True, ledger, emit)
                finally:
                    ledger.close()
        else:
            plan = load_plan(args, settings)
            from video_engine import validate_video_plan
            report = estimate(plan, settings)
            report["capability_checks"] = validate_video_plan(plan, settings, require_keys=False)
            emit(report)
            if args.command in ("estimate", "plan") or not args.allow_paid:
                return 0
            with run_lock(args.out):
                result = render_episode(plan, settings, args.out, args.budget_usd, True, event=emit)
        emit({k: result[k] for k in ("status", "output", "sha256", "cost")})
        return 0
    if args.command == "character" and not args.generate:
        bible = [Character.model_validate(c) for c in json.loads(args.bible.read_text(encoding="utf-8-sig"))]
        emit({"valid": True, "characters": [c.model_dump() for c in bible], "paid_calls": 0})
        return 0
    if args.command in ("image", "character"):
        from image_engine import ImageEngine, rate
        ceiling = rate(settings, "openai:image")
        emit({"stage": "estimate", "image_call_ceiling_usd": ceiling,
              "character_views": "up to three calls per character"})
        if not args.allow_paid:
            return 0
        with run_lock(args.out):
            ledger = Ledger(args.out / "tasks.sqlite3", args.budget_usd, True)
            try:
                write_json(args.out / "run.json", {"budget_usd": args.budget_usd, "settings": settings.model_dump(),
                                                   "command": args.command, "test_only": False})
                engine = ImageEngine(settings, ledger)
                if args.command == "image":
                    if Path(args.filename).name != args.filename or not args.filename.lower().endswith(".png"):
                        raise CinemaError("--filename must be a plain PNG filename")
                    output = engine.generate(args.prompt, args.out / args.filename,
                                             [p.resolve(strict=True) for p in args.reference])
                    emit({"image": str(output.resolve()), "cost": ledger.summary()})
                else:
                    from character_engine import prepare_characters
                    bible = [Character.model_validate(c) for c in json.loads(
                        args.bible.read_text(encoding="utf-8-sig"))]
                    from types import SimpleNamespace
                    prepared = prepare_characters(SimpleNamespace(characters=bible, visual_style=args.style),
                                                   engine, args.out / "characters", args.bible.resolve().parent)
                    emit({"characters": [c.model_dump() for c in prepared], "cost": ledger.summary()})
            finally:
                write_json(args.out / "cost_report.json", ledger.summary())
                ledger.close()
        return 0
    raise CinemaError("Unsupported command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        emit({"status": "interrupted", "note": "Tasks remain on disk. Resume instead of submitting a new run."})
        raise SystemExit(130)
    except Exception as exc:
        # Avoid provider request dumps, environment contents, and HTTP response bodies in logs.
        emit({"status": "error", "type": type(exc).__name__, "error": str(exc)})
        raise SystemExit(2)
