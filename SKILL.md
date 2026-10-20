---
name: cinematic-ai-studio
description: Generate cinematic AI images, live-action movies, animated films, motion comics, dynamic character scenes, and complete AI drama episodes using real video-generation models, consistent characters, synchronized audio, editing, and MP4 delivery. Use when a user requests AI movie generation, animated video creation, film scenes, or complete short dramas.
---

# Cinematic AI Studio

Create the requested film from the user's current creative brief, story, script, references or shot plan. There is no bundled production, fixed cast or default screenplay. Resolve tools relative to this file. Start with `python scripts/cinema.py doctor` and `providers`; read the [provider guide](references/provider-guide.md) for setup and verified adapter capabilities.

## Project boundary

- Create a separate local project for each user's production, outside every Skill installation and repository; for example `E:\SKILL\projects\<project-name>\`. If the user has an existing project, preserve it and its original output directory, budget and task ledger.
- Store that user's story, Character Bible, scene/shot plans, references, generated images/video/audio, subtitles, task records, reviews and costs inside the external project. Never add productions to this repository, documentation, tests, screenshots or release archives. Structure examples describe fields only.
- The CLI defaults new output to a unique directory below `~/CinematicAIStudio/projects/`; `CINEMA_PROJECTS_DIR` can select another external root. An explicit `--out` selects the user's project. Production writes inside a Skill copy are rejected.
- Test fixtures are synthetic technical data. Never load them as a user's story or deliver them as a film.

## Production contract

- Use real video-generation models or authorized actual dynamic footage for narrative shots. Do not substitute stills, slideshows, Ken Burns moves, loops, frozen/black padding or title cards. FFmpeg performs postproduction.
- Preserve the user's requested scope and runtime. Design variable, model-supported durations whose sum exactly matches this production. A preview or single test shot is not a requested complete film.
- Use original/user-authorized references. Preserve Character IDs, identities, wardrobe versions, voices and reference conditioning across shots and episodes; read [character consistency](references/character-consistency.md).
- Paid actions require provider credentials and explicit user authorization with a USD budget. A Key, general movie request or copied example flag is insufficient. Show the reviewed estimate before paid work and encode existing authorization with `--allow-paid --budget-usd AMOUNT`; do not choose or increase the budget.
- Keep unknown/failed charges reserved. Reconcile uncertain submissions using confirmed tasks/results before another purchase. Known tasks resume without resubmission, and retries/revisions stay bounded.

## Build the current production

1. Use the current user's story, requested mode/runtime/format and authorized references to create project-specific Character/Scene Bibles and `shot_plan.json`. Codex may author the JSON directly using `schema plan`, avoiding an extra planner charge. The optional budgeted `--story-file` planner requires the user's explicit `--seconds` and never assumes a fixed story or runtime.
2. Select `live_action`, `anime`, `motion_comic` or `ai_drama`. Read [cinematic style](references/cinematic-style.md) and [shot generation](references/shot-generation.md). Design sequenced actions, expressions, eyelines, focus, camera motion and meaningful transitions.
3. Prefer schema v2: timed action beats, scene IDs, blocking, wardrobe versions, continuity input/output and explained intentional changes. Read [v2 production](references/production-v2.md). `plan --plan PROJECT/shot_plan.json --out PROJECT/render` compiles a local director packet; it does not invent content.
4. Run `estimate` with the user's plan and reviewed config. Once authorized, the executor can create missing reference/first-frame images, submit supported real video jobs, synthesize timed Mandarin dialogue, perform suitable lip sync, mix sound/music, subtitle, edit and export MP4. Record actual models, parameters, task IDs, source hashes and costs.
5. Read [audio pipeline](references/audio-pipeline.md). Keep stable voices and delivery style; measure actual speech fit. Sync requires one visible dubbed speaker; use reverse shots or an explicit supported alternative. Preserve native audio once or replace it once. Disclose disabled/unverified lip sync and unverified anime adaptation.
6. Read [quality control](references/quality-control.md). Motion evidence, sparse-frame vision and planned continuity cannot certify identity, acting, anatomy or mouth-to-speech alignment. Intentional holds/subtle performance and uncertain motion require exact-hash human review. Review uncertain raw video before paying for lip sync; retain raw/synced versions.
7. Use `studio --out PROJECT/render` for local previews, tasks, costs and hash-bound review. It never submits generation. `regenerate` replaces a single shot under the original budget and revision bound; `render` re-edits accepted existing dynamic sources without paid calls.

## Commands

`PROJECT` below is the external directory for the current user input. All commands have `--help`; these examples contain no paid authorization.

```text
python scripts/cinema.py doctor
python scripts/cinema.py providers
python scripts/cinema.py schema plan
python scripts/cinema.py character --bible PROJECT/characters.json
python scripts/cinema.py estimate --plan PROJECT/shot_plan.json --config PROJECT/config.json
python scripts/cinema.py plan --plan PROJECT/shot_plan.json --config PROJECT/config.json --out PROJECT/render
python scripts/cinema.py episode --plan PROJECT/shot_plan.json --config PROJECT/config.json --out PROJECT/render
python scripts/cinema.py shot --plan PROJECT/shot_plan.json --shot-id SHOT_ID --config PROJECT/config.json --out PROJECT/shot-render
python scripts/cinema.py image --prompt "USER_REQUESTED_IMAGE" --config PROJECT/config.json --out PROJECT/images
python scripts/cinema.py inspect PROJECT/render/episode_NN.mp4 --plan PROJECT/shot_plan.json
python scripts/cinema.py studio --out PROJECT/render
python scripts/cinema.py review --out PROJECT/render
python scripts/cinema.py render --out PROJECT/render
```

Generation commands without paid flags estimate only; `plan --plan` can save its explicitly requested local packet. Resume with `resume --out PROJECT/render --allow-paid --budget-usd ORIGINAL_AMOUNT`. Never create a new directory to evade a prior uncertain charge.

## Deliver

Return the user's full requested MP4 and project reports: manifest, QC, quality review, costs, characters, scenes, shot plan, director/continuity/edit data and subtitles. Disclose native versus post-upscaled resolution and unresolved audiovisual review items. Output numbering `episode_NN.mp4` follows the user's plan, not a bundled episode.

Keep **Offline Tested**, **Media Pipeline Verified**, **Provider Live Verified**, **Full Episode Rendered** and **Editorially Reviewed** distinct. Missing real evidence stays Pending. Offline exports are `TEST_ONLY_`, with `test_only=true` and `real_model_generation=false`, and never count as a movie. No API keys or billing permission are bundled.
