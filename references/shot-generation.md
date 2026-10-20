# User stories and moving-shot plans

Run `python scripts/cinema.py schema plan`; `scripts/models.py` defines the canonical schema. Use the current user's creative brief/story/script and requested scope to author a project-specific plan outside the Skill repository. No default screenplay or production plan is shipped. `assets/characters.example.json` describes character fields only; test fixtures are never production inputs.

Each shot specifies a unique ID, visible Character IDs, model-supported duration, subject, sequenced action, facial expression, environment, camera framing/movement, lighting, temporal development, continuity, dialogue windows, sound cues and generation controls. Describe changes over time rather than a stationary portrait. The sum of shot durations must exactly cover the user's requested runtime, with no repeated/frozen/black picture padding.

`video_prompt()` includes Subject, Character Identity, Character Action, Facial Expression, Environment, Camera Movement, Lighting, Visual Style, Temporal Motion and Negative Constraints. In v2 it compiles timed action beats and blocking/direction. Keep fields concise enough for the selected model's prompt limit; necessary actions are never silently truncated.

`image_to_video` creates a scene first frame from character references unless one is supplied. `text_to_video` calls the actual endpoint and rejects unsupported frame/Element controls. Last-frame control requires a first frame and a supported model. A scene image alone is not video evidence. Authorize every supplied image/video/audio and store it in the local project.

`episode --story-file PROJECT/story.txt --seconds REQUESTED_SECONDS --mode SELECTED_MODE --out PROJECT/render` is an optional, separately budgeted planner. Runtime is explicit and content comes only from that user's source. Local schema/runtime/control checks apply; the planner may not invent external asset paths. Failed validation retains its paid result for review rather than triggering unlimited rewrites. Codex-authored `--plan PROJECT/shot_plan.json` avoids this planning API call.

`plan --plan ... --out PROJECT/render` compiles the user's local director packet. `shot --plan ... --shot-id SHOT_ID --out PROJECT/shot-render` executes a selected shot, which remains an excerpt. Resume preserves original inputs/budget and reuses verified outputs or existing task IDs. A changed plan is an explicit revision/new production, never an excuse to repeat an unknown purchase.
