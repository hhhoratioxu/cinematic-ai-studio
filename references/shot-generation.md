# Plan and moving-shot contract

Run `python scripts/cinema.py schema plan`; the canonical schema is generated from `scripts/models.py`. The complete supplied episode is `assets/episode01.plan.json`. Codex can author this JSON directly without paying a separate planner model.

Every shot specifies: unique ID; appearing Character IDs; integer duration; subject; sequenced physical action; facial expression; place/time; camera framing/movement; lighting; temporal action development; continuity into adjacent shots; dialogue windows; sound cues; generation method and optional first/last frames or Elements. Avoid descriptions of a person merely standing in a room. Include what changes at the start, middle and end, such as stepping toward a desk, turning to a speaker, tightening a hand and then answering.

`video_prompt()` includes Subject, Character Identity, Character Action, Facial Expression, Environment, Camera Movement, Lighting, Visual Style, Temporal Motion and Negative Constraints. Keep each field concise so the full prompt fits the provider's actual character limit. The complete identity description also conditions the scene image. Prompt text is never silently sliced to fit.

`generation=image_to_video` creates a scene image using character references unless `first_frame` is supplied. `text_to_video` does not manufacture an image fallback; it calls the actual text-video endpoint and rejects incompatible reference controls. `last_frame` is allowed only with a first frame and a supported model. Scene image generation is not itself video evidence.

`episode --story-file STORY.txt --seconds 180 --mode ai_drama` uses a budgeted OpenAI Responses planner. Its output must pass the same local schema and coverage checks. The planner is not permitted to invent local asset paths. If planning fails semantic/schema validation, the raw result remains available for review; it does not trigger an unbounded paid rewrite loop.

`shot --plan PLAN --shot-id s001` executes one existing shot through the same video, audio and export route; use a separate output directory. A shot run is an excerpt and must not be delivered as the user's requested full episode.

Resume preserves the original plan/settings/budget. Successful tasks reuse validated files; damaged cached asynchronous outputs are downloaded again from the existing task, and only terminally failed or QC-rejected tasks permit the next bounded attempt. Provider mismatch, unsupported controls and missing keys are reported. Connection uncertainty and unfinished known tasks stop rather than triggering a competing fallback generation.
