---
name: cinematic-ai-studio
description: Generate cinematic AI images, live-action movies, animated films, motion comics, dynamic character scenes, and complete AI drama episodes using real video-generation models, consistent characters, synchronized audio, editing, and MP4 delivery. Use when a user requests AI movie generation, animated video creation, film scenes, or complete short dramas.
---

# Cinematic AI Studio

Use this skill's Python tools to produce original characters, images, moving shots, and complete episodes. Resolve `scripts/` relative to this file, and keep production projects outside the installed skill. Run `python scripts/cinema.py doctor` and `providers` first; see [provider guide](references/provider-guide.md) for keys, capabilities and setup.

## Production contract

- Narrative footage must come from a real video-generation API. Do not replace a failed shot with a still, slideshow, Ken Burns move, loop, title card, freeze or black padding. FFmpeg performs postproduction only.
- Preserve requested runtime and episode scope. A 180-second first episode needs its full conflict, development, reversal and ending, with shot durations totaling 180. A test excerpt is not that episode.
- Use original characters or user-authorized reference images. Preserve their Character IDs, wardrobe, voice IDs and reference images across shots and episodes. Read [character consistency](references/character-consistency.md).
- Run all ordinary development/tests offline. Paid calls require configured provider keys **and explicit user authorization with a USD budget**. An API key, a general movie request, and the presence of `--allow-paid` in an example do not independently authorize spending. Never choose a budget for the user.
- Before paid work, show `estimate` output with the reviewed rates and scope. `--allow-paid --budget-usd AMOUNT` encodes the user's existing authorization; do not repeatedly ask when it is already sufficient. If a rate is unknown, resolve it from current official pricing and the user's account before populating the cost ceiling.
- Uncertain submissions keep their reservation and stop. Use `reconcile` with a confirmed existing task/result; never clear the ledger or resubmit to guess whether the first request was charged. Never silently change the authorized budget on resume.

## Work with Codex

1. Translate the story into a Character Bible and validated `shot_plan.json`. Use `python scripts/cinema.py schema plan` and [shot generation](references/shot-generation.md). Codex can author this plan directly without an extra planner API call. For unattended CLI story planning use `episode --story-file ...`, which charges a separately reserved OpenAI planner call before estimating the planned assets.
2. Select `live_action`, `anime`, `motion_comic`, or `ai_drama`; use `visual_style` to choose live action or animation within drama. Direct sequenced body and facial actions, expressive reactions and motivated camera choices. Read [cinematic style](references/cinematic-style.md).
3. Use `estimate --plan PROJECT/shot_plan.json --config PROJECT/config.json`, then the matching `episode` command with the already-authorized budget. The executor generates missing character views and scene first frames, submits real video jobs, synthesizes timed Mandarin voices, optionally performs lip sync, mixes licensed/original audio, creates subtitles and exports MP4.
4. For voice/timing decisions read [audio pipeline](references/audio-pipeline.md). Default Sync lip-sync shots require one visible speaker. Use reverse shots and separate interaction shots; keep additional speakers offscreen where appropriate. Disabling lip sync must be disclosed as unsynchronized dubbing. Native audio is either preserved once or replaced once.
5. Read [quality control](references/quality-control.md), inspect per-shot/final reports and review the actual film. Technical success does not establish correct identity, anatomy, acting, subtitle glyph rendering or mouth-to-speech alignment. Sparse-frame vision checks report uncertainty. Regenerate only rejected shots within the configured retry and budget limits.
6. For v0.5 production, read [director, continuity, routing and workbench](references/production-v2.md). Prefer schema v2 with timed action beats, scene IDs, blocking/eyelines/focus, costume versions and explicit continuity states. `plan` writes a reviewable local packet. `studio --out PROJECT` opens the private local workbench; its review actions never buy generation. `status`, `cost` and `review` inspect saved evidence; `render` re-edits accepted dynamic sources locally. `regenerate` replaces exactly one shot under the original explicit budget and bounded revision count.
7. Treat motion heuristics as triage: camera-compensated optical flow and region residuals may flag planar pan/zoom, repeated content or uncertain subject motion. A held close-up, subtle performance or ambiguous result requires exact-hash human review. Review uncertain raw footage before paying for lip sync. Preserve all raw/synced versions and costs. Never equate motion metrics or the software version with cinematic acceptance.

## Commands

All entry points have `--help`. These examples contain no paid authorization:

```text
python scripts/cinema.py doctor
python scripts/cinema.py providers
python scripts/cinema.py schema plan
python scripts/cinema.py character --bible PROJECT/characters.json
python scripts/cinema.py estimate --plan assets/episode01.plan.json --config PROJECT/config.json
python scripts/cinema.py episode --plan PROJECT/shot_plan.json --config PROJECT/config.json --out PROJECT/render
python scripts/cinema.py shot --plan PROJECT/shot_plan.json --shot-id s001 --config PROJECT/config.json --out PROJECT/shot_s001
python scripts/cinema.py image --prompt "Original cinematic character" --config PROJECT/config.json --out PROJECT/images
python scripts/cinema.py inspect PROJECT/render/episode_01.mp4 --plan PROJECT/shot_plan.json
python scripts/cinema.py studio --out PROJECT/render
python scripts/cinema.py review --out PROJECT/render
python scripts/cinema.py render --out PROJECT/render
```

Without `--allow-paid`, generation commands estimate only. After user authorization, add `--allow-paid --budget-usd AMOUNT`. Resume an episode with `resume --out PROJECT/render --allow-paid --budget-usd ORIGINAL_AMOUNT`.

## Deliver

Return the full MP4 and links to `manifest.json`, `qc_report.json`, `cost_report.json`, `characters.json`, `shot_plan.json`, and subtitles. Mention native versus post-upscaled resolution and all unresolved review items. Output names are `episode_NN.mp4`; standalone shot runs also retain source clips under `shots/SHOT_ID/`. Offline demonstrations are always `TEST_ONLY_episode_NN.mp4` with `real_model_generation=false` and cannot be accepted as a film.

Use the complete 180-second example [episode01.plan.json](assets/episode01.plan.json) for 《被开除后，我的真实身份曝光了》第一集, or adapt its story with the same full-episode scope. No API keys or billing permission are bundled.
