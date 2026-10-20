"""A complete episode pipeline; production never falls back to synthetic footage."""
from __future__ import annotations

import concurrent.futures
import threading
from pathlib import Path

from audio_engine import AudioEngine, original_score, subtitles
from character_engine import prepare_characters
from common import CinemaError, TaskFailed, content_key, digest, write_json
from compatibility import snapshots as input_snapshots
from continuity_engine import effective_cast, require_continuity
from director_engine import production_packet
from editing_engine import export_episode, normalize_shot
from image_engine import ImageEngine, rate
from models import Plan, Settings
from providers.base import AsyncJobs
from providers.sync_lipsync import SyncLipsync
from quality_control import inspect_episode, inspect_video, require_pass
from state import Ledger
from video_engine import VideoEngine, decoded_signature, validate_video_plan


def process_shot(plan, shot, settings, ledger, directory, revision=None):
    """One independently cacheable unit, also used by bounded local regeneration."""
    import json
    from workspace import ensure_external_project
    directory = ensure_external_project(directory)
    from shutil import copy2
    root = directory / "shots" / shot.id
    if revision:
        root = root / "revisions" / str(revision)
    root.mkdir(parents=True, exist_ok=True)
    accepted = root / "accepted.json"
    if accepted.is_file():
        entry = json.loads(accepted.read_text(encoding="utf-8"))
        normalized = Path(entry.get("normalized_file", directory / "normalized" / f"{shot.id}.mkv"))
        if normalized.is_file() and digest(normalized) == entry.get("normalized_sha256") and Path(entry["source_file"]).is_file() and digest(Path(entry["source_file"])) == entry["source_sha256"]:
            return normalized, entry, entry.get("dialogue_timing", [])
        raise CinemaError(f"{shot.id}: accepted asset changed/missing; restore it or explicitly regenerate")
    cast = effective_cast(plan, shot) if not shot.source_video else []
    audio = AudioEngine(settings, ledger)
    spoken, timing = audio.dialogue(shot, plan.characters, root / "audio")
    if shot.source_video:
        # Preserve the imported original in the run, so editing is independent of external paths.
        video = root / "imported_source.mp4"
        copy2(shot.source_video, video)
        qc = inspect_video(video, settings, duration=shot.duration,
                           require_audio=shot.native_audio == "preserve", shot=shot)
        require_pass(qc, shot.id)
        provenance = {"shot_id": shot.id, "provider": "user", "model": None, "task_id": None,
                      "evidence": "user_supplied_dynamic_video", "source_license": shot.source_license,
                      "qc": qc, "origin": str(Path(shot.source_video).resolve())}
    else:
        first = Path(shot.first_frame) if shot.first_frame else None
        if shot.generation == "image_to_video" and not first:
            first = ImageEngine(settings, ledger).scene(plan, shot, cast, directory / "scenes")
        engine = VideoEngine(settings, ledger)
        if revision:
            video, provenance = engine.generate(plan, shot, cast, first, root, revision=revision)
        else:
            video, provenance = engine.generate(plan, shot, cast, first, root)
    provenance["generated_file"] = str(video)
    provenance["generated_sha256"] = digest(video)
    if settings.lipsync == "sync" and shot.native_audio == "replace" and any(
            d.delivery == "onscreen" for d in shot.dialogue):
        if len(shot.characters) != 1 or len({d.character for d in shot.dialogue if d.delivery == "onscreen"}) != 1:
            raise CinemaError("Sync requires one visible speaker; cut reverse shots or explicitly choose lipsync=off")
        # A static/uncertain source must be reviewed before a second paid transformation.
        motion = provenance.get("qc", {}).get("motion", {})
        if motion.get("status") == "needs_review":
            from project import has_approval
            if not has_approval(directory, shot.id, digest(video), "motion"):
                raise CinemaError(f"{shot.id}: motion needs review before paid lip sync; use review --scope motion on the raw video")
        sync_spec = {"model": settings.lipsync_model, "video": str(video), "audio": str(spoken),
                     "video_sha256": digest(video), "audio_sha256": digest(spoken)}
        jobs = AsyncJobs(ledger, settings.poll_seconds, settings.task_timeout_seconds)
        for attempt in range(settings.max_attempts):
            try:
                synced, sync_key = jobs.run(SyncLipsync(), sync_spec, root / f"lipsync_{attempt + 1}.mp4",
                    rate(settings, "sync:lipsync", shot.duration), kind="lipsync", attempt=attempt)
            except TaskFailed:
                if attempt + 1 == settings.max_attempts:
                    raise
                continue
            qc = inspect_video(synced, settings, duration=shot.duration, shot=shot)
            write_json(root / f"qc_lipsync_{attempt + 1}.json", qc)
            if qc["technical_pass"]:
                video = synced
                provenance["lipsync"] = {"task_key": sync_key, "task_id": ledger.get(sync_key)["task_id"],
                                         "file": str(synced), "sha256": digest(synced),
                                         "qc": qc, "accuracy": "requires audiovisual review"}
                break
            ledger.update(sync_key, state="rejected", error=",".join(qc["issues"]))
        else:
            raise CinemaError(f"{shot.id}: lip-sync QC exhausted bounded attempts")
    tracks = audio.sound_tracks(shot, root / "audio")
    tracks.insert(0, {"file": video if shot.native_audio == "preserve" else spoken, "start": 0, "gain_db": 0})
    if shot.edit.audio_fade:
        tracks[0].update(duration=shot.duration, fade_in=shot.edit.audio_fade, fade_out=shot.edit.audio_fade)
    mixed = audio.mix(shot.duration, tracks, root / "audio" / "mixed.wav")
    normalized = root / "normalized.mkv" if revision else directory / "normalized" / f"{shot.id}.mkv"
    provenance["postprocessing"] = normalize_shot(video, mixed, normalized, shot, plan.output, settings)
    provenance.update(normalized_file=str(normalized), normalized_sha256=digest(normalized),
        decoded_signature=decoded_signature(video, settings), source_file=str(video), source_sha256=digest(video),
        mixed_audio=str(mixed), mixed_audio_sha256=digest(mixed),
        dialogue_timing=[{**r, "file": str(r["file"])} for r in timing], revision=revision,
        shot_spec=shot.model_dump(), shot_spec_sha256=content_key(shot.model_dump()))
    write_json(accepted, provenance)
    return normalized, provenance, timing


def music_bus(plan, settings, directory):
    """Original/licensed cues can overlap to create audio crossfades on the episode timeline."""
    bed = Path(plan.music_file) if plan.music_file else None
    if not bed and plan.original_score:
        bed = original_score(directory / "audio" / "original_ambient_score.wav", plan.target_seconds)
    if not plan.music_cues:
        return bed
    tracks = []
    for cue in plan.music_cues:
        source = Path(cue.file) if cue.file else bed
        if not source:
            raise CinemaError(f"Music cue {cue.id} has no licensed file or original score")
        tracks.append({"file": source, "start": cue.start, "duration": cue.end - cue.start,
                       "gain_db": cue.gain_db, "fade_in": cue.fade_in, "fade_out": cue.fade_out})
    # mix() is completely local and does not instantiate a model client.
    return AudioEngine(settings, None).mix(plan.target_seconds, tracks, directory / "audio" / "music_cues.wav")


def estimate(plan: Plan, settings: Settings):
    items = []
    missing = set()
    def add(label, unit, units):
        value = settings.ceilings_usd.get(unit)
        if value is None:
            missing.add(unit)
        items.append({"item": label, "rate_key": unit, "units": units,
                      "ceiling_usd": None if value is None else round(value * units, 6)})
    for c in plan.characters:
        if not any(c.id in s.characters and not s.source_video for s in plan.shots):
            continue
        for view in ("front", "side", "full_body", *c.expression_views):
            if view not in c.references:
                add(f"character:{c.id}:{view}", "openai:image", 1)
    for shot in plan.shots:
        if not shot.source_video and shot.generation == "image_to_video" and not shot.first_frame:
            add(f"scene:{shot.id}", "openai:image", 1)
        from capabilities import route
        choices, _ = route(plan, shot, settings) if not shot.source_video else ([], [])
        for config, _ in choices:
            add(f"video:{shot.id}:{config.name}", f"{config.name}:video:{config.model}",
                shot.duration * settings.max_attempts)
        if settings.vision_qc and not shot.source_video:
            add(f"vision:{shot.id}", "openai:vision", settings.max_attempts * len(settings.video))
        if shot.native_audio == "replace":
            for i, _ in enumerate(shot.dialogue):
                add(f"dialogue:{shot.id}:{i}", "openai:tts", 1)
            if settings.lipsync == "sync" and any(d.delivery == "onscreen" for d in shot.dialogue):
                add(f"lipsync:{shot.id}", "sync:lipsync", shot.duration * settings.max_attempts)
        for sound in shot.sounds:
            if not sound.file:
                add(f"sound:{shot.id}:{sound.id}", "runway:sfx", sound.duration)
    total = None if missing else round(sum(item["ceiling_usd"] for item in items), 6)
    return {"target_seconds": plan.target_seconds, "shot_count": len(plan.shots),
            "all_attempts_and_configured_fallbacks_ceiling_usd": total, "missing_rates": sorted(missing),
            "items": items, "actual_billed_usd": None,
            "note": "Upper-bound reservations from your reviewed rates; no vendor price is inferred. "
                    "Includes bounded video/lipsync retries and fallback providers, excludes optional story "
                    "planning (separate reservation). Provider invoices determine actual charges."}


def check_environment(plan, settings):
    import os
    validate_video_plan(plan, settings)
    require_continuity(plan)
    for shot in plan.shots:
        if not shot.source_video:
            effective_cast(plan, shot)
    needs_openai = any(not all(k in c.references for k in ("front", "side", "full_body"))
                       for c in plan.characters if any(c.id in s.characters and not s.source_video for s in plan.shots))
    needs_openai |= any(not s.source_video and s.generation == "image_to_video" and not s.first_frame for s in plan.shots)
    needs_openai |= (settings.vision_qc and any(not s.source_video for s in plan.shots)) or any(s.dialogue and s.native_audio == "replace" for s in plan.shots)
    if needs_openai and not os.environ.get("OPENAI_API_KEY"):
        raise CinemaError("OPENAI_API_KEY required for planned images, speech or vision checks")
    if any(not sound.file for s in plan.shots for sound in s.sounds) and not os.environ.get("RUNWAYML_API_SECRET"):
        raise CinemaError("RUNWAYML_API_SECRET required for generated sound effects; alternatively import licensed files")
    if settings.lipsync == "sync" and any(s.native_audio == "replace" and
            any(d.delivery == "onscreen" for d in s.dialogue) for s in plan.shots):
        if not os.environ.get("SYNC_API_KEY"):
            raise CinemaError("SYNC_API_KEY required for on-screen dubbed speech; explicit lipsync=off permits "
                              "unsynchronized dubbing with manual-review status")
    report = estimate(plan, settings)
    if report["missing_rates"]:
        raise CinemaError("Configure cost ceilings: " + ", ".join(report["missing_rates"]))
    from common import media_capabilities, media_tool
    media_tool("ffmpeg", settings.ffmpeg)
    media_tool("ffprobe", settings.ffprobe)
    capabilities = media_capabilities(settings)
    missing_filters = set(capabilities["missing_filters"])
    if not plan.output.burn_subtitles:
        missing_filters.discard("ass")
    if missing_filters or capabilities["missing_encoders"]:
        raise CinemaError("FFmpeg is missing required filters/encoders: " +
                          ", ".join(sorted(missing_filters) + capabilities["missing_encoders"]) +
                          ". On macOS install ffmpeg-full (libass), or specify a full FFmpeg build.")
    return report


def render_episode(plan: Plan, settings: Settings, directory: Path, budget: float, authorized: bool,
                   ledger: Ledger | None = None, event=None):
    from fonts import select_font
    needs_subtitles = plan.output.burn_subtitles and any(s.dialogue for s in plan.shots)
    plan = plan.model_copy(update={"output": select_font(plan.output, needed=needs_subtitles)})
    from workspace import ensure_external_project
    directory = ensure_external_project(directory)
    directory.mkdir(parents=True, exist_ok=True)
    edit = directory / "edit"
    edit.mkdir(exist_ok=True)
    subtitles(plan, edit)  # Reject unsafe line lengths before paying for any generated assets.
    report = check_environment(plan, settings)
    write_json(directory / "estimate.json", report)
    own_ledger = ledger is None
    ledger = ledger or Ledger(directory / "tasks.sqlite3", budget, authorized)
    snapshots = {"plan": plan.model_dump(), "settings": settings.model_dump()}
    external_files = [Path(v) for c in plan.characters for v in c.references.values()]
    external_files += [Path(v) for s in plan.shots for v in (s.first_frame, s.last_frame) if v]
    external_files += [Path(sound.file) for s in plan.shots for sound in s.sounds if sound.file]
    external_files += [Path(plan.music_file)] if plan.music_file else []
    external_files += [Path(s.source_video) for s in plan.shots if s.source_video]
    external_files += [Path(c.file) for c in plan.music_cues if c.file]
    external_files += [Path(v) for c in plan.characters for refs in c.reference_sets.values() for v in refs.values()]
    fingerprint = {"inputs": input_snapshots(plan, settings), "files": {str(p): digest(p) for p in external_files}}
    ledger.bind("production_inputs", content_key(fingerprint))
    write_json(directory / "run.json", {**snapshots, "budget_usd": budget, "test_only": False})
    notify = event or (lambda value: None)
    write_json(directory / "manifest.json", {"status": "in_progress", "test_only": False, "shots": []})
    try:
        production_packet(plan, directory)
        needed = {cid for s in plan.shots if not s.source_video for cid in s.characters}
        prepare = plan.model_copy(update={"characters": [c for c in plan.characters if c.id in needed]})
        prepared = prepare_characters(prepare, ImageEngine(settings, ledger), directory / "characters", directory)
        by_id = {c.id: c for c in prepared}
        characters = [by_id.get(c.id, c) for c in plan.characters]
        working = plan.model_copy(update={"characters": characters})
        write_json(directory / "shot_plan.json", working.model_dump())
        results = {}
        cancellation = threading.Event()
        def process(shot):
            if cancellation.is_set():
                raise CinemaError("Stopped after another shot failed; resume will reuse accepted shots")
            notify({"stage": "shot", "shot": shot.id})
            result = process_shot(working, shot, settings, ledger, directory)
            notify({"stage": "accepted", "shot": shot.id})
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.max_concurrency) as pool:
            futures = {pool.submit(process, shot): shot.id for shot in working.shots}
            try:
                for future in concurrent.futures.as_completed(futures):
                    results[futures[future]] = future.result()
            except BaseException:
                cancellation.set()
                for future in futures:
                    future.cancel()
                raise
        ordered = [results[shot.id] for shot in working.shots]
        if any(entry[1]["evidence"] not in ("real_api_video", "user_supplied_dynamic_video") for entry in ordered):
            raise CinemaError("Synthetic/mock footage cannot enter a production episode")
        signatures = [entry[1]["decoded_signature"] for entry in ordered]
        if len(set(signatures)) != len(signatures):
            raise CinemaError("Duplicate decoded shot content detected; no completed episode exported")
        edit = directory / "edit"
        edit.mkdir(exist_ok=True)
        srt, ass = subtitles(working, edit, {s.id: results[s.id][2] for s in working.shots})
        music = music_bus(working, settings, directory)
        final = export_episode([entry[0] for entry in ordered], working, edit, settings, music)
        qc = inspect_episode(final, working, settings)
        qc["shot_coverage"] = {"expected": len(working.shots), "accepted": len(ordered),
                                "missing": [], "duplicate_decoded_shots": False}
        write_json(directory / "qc_report.json", qc)
        require_pass(qc, "final_episode")
        manifest = {"version": 1, "status": "rendered_requires_editorial_review", "test_only": False,
                    "title": plan.title, "episode": plan.episode, "mode": plan.mode,
                    "target_seconds": plan.target_seconds, "output": str(final), "sha256": digest(final),
                    "shots": [entry[1] for entry in ordered], "technical_qc": qc,
                    "subtitles": str(srt), "music": {"file": str(music) if music else None,
                        "rights": plan.music_license if plan.music_file else "original procedural ambient score"},
                    "disclosure": "AI-generated footage and synthetic voices. Technical QC does not certify "
                                  "identity, acting, anatomy, lip-sync, subtitle glyph bounds or cinematic quality.",
                    "cost": ledger.summary()}
        write_json(directory / "manifest.json", manifest)
        from project import quality_review
        quality_review(directory, manifest=manifest)
        return manifest
    except BaseException as e:
        write_json(directory / "manifest.json", {"status": "incomplete", "test_only": False,
                   "error": str(e), "cost": ledger.summary(),
                   "accepted_shots": [p.parent.name for p in (directory / "shots").glob("*/accepted.json")]})
        raise
    finally:
        write_json(directory / "cost_report.json", ledger.summary())
        if own_ledger:
            ledger.close()
