# Direction by visual mode

`mode` is one of `live_action`, `anime`, `motion_comic`, `ai_drama`. `visual_style` supplies the common art direction. It is included in character views, scene compositions and every video prompt.

Live action: choose original performers, plausible skin/wardrobe detail, a consistent light source and believable weight/inertia. Prioritize head/body action and readable emotion before complex camera choreography.

Anime: anchor silhouette, facial proportions, hair shapes, palette and rendering style. Request articulated body animation, expressions, secondary hair/clothing movement and changing poses over time. Still painted frames plus camera movement do not establish character animation.

Motion comic: keep ink, shading, palette and panel-inspired framing consistent while generating real walking, turning, interaction and mouth/expression changes. Comic effects may supplement motion; printed panels never replace it.

AI drama: choose either a live-action or anime `visual_style`. Construct conflict → reaction → new evidence → confrontation → reversal → unresolved consequence. Preserve scene geography and direction of looks across reverse shots. The CLI validates technical coverage; Codex and an editor must assess whether the actual story earns each beat.

Camera choices have a purpose: establishing/wide for geography and blocking; medium for gestures; close-up/extreme close-up for emotional revelation; over-shoulder for confrontation; tracking for motivated travel; dolly in/out for changing emotional pressure; pan/tilt to reveal a subject; handheld for instability; low/high angles for status. The schema supports all these choices. Avoid an arbitrary camera effect in every shot.

Defaults are 9:16, 1080×1920, 24 fps, Mandarin, Simplified Chinese, H.264/AAC MP4. A plan's integer shot durations must exactly cover the requested runtime. Choose 16:9 (e.g. 1920×1080) or another verified provider ratio through `output`. Native model dimensions are recorded separately from Lanczos resampling in postproduction.
