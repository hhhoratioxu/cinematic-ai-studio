# Provider setup and verified contracts

Documentation checked 2026-10-20. Account access and regional availability still need live verification by the person running production. No paid acceptance was performed for this release. Model names are explicit configuration, not inferred newest models.

Install Python 3.11+ and FFmpeg with FFprobe and libx264/libass. From the skill directory:

```text
python -m venv .venv
python -m pip install -r requirements.txt
python scripts/cinema.py doctor
```

Activate the virtual environment first, or use its Python executable for the second/third commands. Windows: `.venv\Scripts\python.exe`; macOS: `.venv/bin/python`. FFmpeg: Windows `winget install --id Gyan.FFmpeg --exact`; macOS `brew install ffmpeg-full`; Ubuntu `sudo apt-get install ffmpeg fonts-noto-cjk`. Homebrew's [full formula](https://formulae.brew.sh/formula/ffmpeg-full) includes libass; its basic formula may omit subtitle rendering. The tool prefers the full formula's keg path and `doctor` checks required filters/encoders before production. `CINEMA_FFMPEG`, `CINEMA_FFPROBE`, and `CINEMA_FONT` can name local files. On Windows the tool also finds Gyan's WinGet installation before PATH refresh. No custom driver or security bypass is involved.

Keep keys in environment variables, never JSON/source/git. PowerShell example: `$env:OPENAI_API_KEY = 'YOUR_KEY'`; macOS: `export OPENAI_API_KEY='YOUR_KEY'`. Do not paste real keys into shared logs or chat.

| Adapter | Environment | Implemented official endpoints / constraints |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `/v1/images/generations`, `/v1/images/edits` (multipart `image[]`), `/v1/audio/speech`, `/v1/responses` |
| Runway | `RUNWAYML_API_SECRET` | `/v1/text_to_video`, `/v1/image_to_video`, `/v1/tasks/{id}`, `/v1/sound_effect`; header `X-Runway-Version: 2024-11-06` |
| Kling | `KLING_API_KEY`, or legacy `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | Singapore official `/v1/videos/text2video`, `/v1/videos/image2video`, matching GET task endpoints; Bearer API key or HS256 JWT |
| Sync | `SYNC_API_KEY` | Multipart `/v2/generate`, GET `/v2/generate/{id}`; existing dynamic MP4 and timed WAV, `Idempotency-Key` |

OpenAI defaults: `gpt-image-1.5`, `gpt-4o-mini-tts`, `gpt-4.1-mini` for planning/vision. These are documented model IDs, not a claim about the newest model. Image references use edits; the first view anchors subsequent views and scene compositions. The image size is explicitly configured. TTS outputs WAV; Responses uses JSON mode with local schema validation and `store=false`.

Runway: `gen4.5` supports text-to-video and first-frame image-to-video, integer 2–10 seconds. `gen4_turbo` requires an image. `veo3.1` and `veo3.1_fast` permit a first/last frame with 4, 6 or 8 seconds. Frame/ratio capabilities depend on model; unsupported controls fail before submission. Gen prompts have a 1000 UTF-16 unit ceiling and are rejected rather than silently truncated. Sound effects use `eleven_text_to_sound_v2`. Poll no more often than every 5 seconds.

Kling: verified supported legacy contract, not its newer API. `kling-v2-6` is conservatively limited to 5/10-second shots; `kling-v3` supports 3–10-second shots in this pipeline. Local images are raw Base64, without a data URL prefix. First/last frames use `image` / `image_tail`. Existing Element library IDs can be supplied to Kling 3 image-to-video through `elements`; creating a new library element is outside this adapter. `external_task_id` is persisted as a correlation ID, **not** assumed to be an idempotency guarantee. Capability restrictions remain account/model specific.

Sync: `lipsync-2` / `lipsync-2-pro` are integrated via verified file upload. The pipeline never sends a still image to this service in place of a real source video. Single-visible-speaker shots avoid ambiguous face selection. It does not use a loop mode to change the shot's length. Model support for stylized anime/comics requires real acceptance; fail or request an explicit disclosed no-lipsync mode if unsuitable.

Copy `assets/config.example.json` into the project and populate `ceilings_usd` with **reviewed upper bounds** for your exact models, dimensions, quality, reference-input limits and account prices:

| Rate key | Unit reserved |
|---|---|
| `openai:image` | per call, including text/reference inputs |
| `openai:tts` | per utterance, up to 300 characters |
| `openai:planner` | per story planning call, bounded output tokens |
| `openai:vision` | per sparse-frame review call |
| `runway:video:gen4.5` | per generated second (use the selected model ID in the key) |
| `kling:video:kling-v2-6` | per generated second (use the selected model ID) |
| `runway:sfx` | per generated sound second |
| `sync:lipsync` | per source shot second |

Example syntax only: `"ceilings_usd": {"openai:image": 1.0, "runway:video:gen4.5": 0.5}`. These are deliberately **not vendor price claims**; fill all required entries from current official pricing and your actual account. Production refuses missing or nonpositive rates. Add fallback providers only if their account access, capabilities and costs are authorized; the full retry/fallback envelope is included in the estimate.

The local ledger atomically stops a new submission whose reservation would exceed the authorized total. It records provider-reported cost metadata when returned, keeps failed/uncertain charges reserved, and reports `actual_billed_usd=null` when no trustworthy invoice amount is available. A local reservation is not a provider-enforced dollar cap: an underestimated rate, price change or external account use can affect the invoice. Set matching account-level spending controls where available. Never describe the local estimate as a guaranteed vendor bill.

On interruption keep the entire output directory and its SQLite database. `resume` polls known task IDs, refreshes signed result URLs and continues partial downloads. A lost synchronous image/TTS/planner response cannot automatically be fetched by task ID; use `reconcile --import-file` with the confirmed result or leave it pending. A lost asynchronous submission can use `reconcile --task-id CONFIRMED_ID --task-key KEY --out RUN --note EVIDENCE`. Do not fabricate a recovery task ID or delete the paid-action ledger.

Official sources: [OpenAI images](https://developers.openai.com/api/docs/guides/image-generation), [image edits](https://developers.openai.com/api/reference/resources/images/methods/edit), [speech](https://developers.openai.com/api/docs/guides/text-to-speech), [Responses](https://developers.openai.com/api/reference/resources/responses/methods/create), [Runway reference/OpenAPI](https://docs.dev.runwayml.com/api/), [Runway input requirements](https://docs.dev.runwayml.com/assets/inputs/), [Runway pricing](https://docs.dev.runwayml.com/guides/pricing/), [Kling authentication](https://kling.ai/document-api/api/get-started/authentication), [Kling image-to-video](https://kling.ai/document-api/api/video/2-6/image-to-video/legacy), [Kling text-to-video](https://kling.ai/document-api/api/video/2-6/text-to-video/legacy), [Kling capability map](https://kling.ai/document-api/guides/capability-map/video), [Sync upload](https://sync.so/docs/api-reference/api/generate-api/create-with-files).

Kling's page body is client-rendered. The integration was checked against the official page's publicly served API definition modules, including the `create-image-to-video`, `create-text-to-video` and task-query schemas. No third-party API gateway or reverse-engineered private endpoint is used.
