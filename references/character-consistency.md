# Character Bible

`characters.json` is an array of validated Character objects. Use `schema character` for the full contract. Fix Character ID, name, age, face, hair, height/build, wardrobe/accessories, temperament, voice, visual style and view references. Generated views are `front`, `side`, `full_body`; imported views are resolved relative to their JSON source.

The engine creates a front reference first and uses it as an edit reference for later views. Scene first frames use the corresponding front references and identity descriptions. Video requests include the scene first frame and identity prompt. Kling 3 can additionally consume existing authorized Element IDs. Text-only shots retain identity text but have weaker visual anchoring, which must be disclosed when selected for recurring characters.

Keep the same project Bible for subsequent episodes. Pass `--bible PREVIOUS_RUN/characters.json` alongside a new episode plan. Reused IDs reject changed face, hair, build, voice or style. Version 2 adds `description`, `costumes`, `wardrobe_version`, `reference_sets`, `expression_views`, `relationships`, `story_state`, `speech_style` and intended `speech_speed`. A deliberate wardrobe change retains the Character ID, declares a new costume version and supplies a matching front reference. Versioned scene conditioning will not silently feed the old outfit image. Existing named costume descriptions are immutable; add a new version instead.

Additional `expression_views` are generated as separately reserved reference edits. The default front/side/full-body workflow remains compatible. Story state and relationships describe intended drama, not an automated observation of the returned actor. Scene Bible and per-shot continuity states track layout, time, lighting, axis, positions, gaze, props, costumes, hair and behavior; unexplained state changes across adjacent shots of the same scene block production.

Character conditioning is a request to the model, not proof of continuity. Inspect first/middle/last frames against references and review the whole shot. Optional paid vision checks flag identity/anatomy/action concerns with sparse-frame uncertainty. A full visual review remains necessary before claiming the actor is consistent throughout the film.

Cache keys include generation settings, prompts and reference content hashes. Keep generated images and the task ledger together. Imported images, music and effects must be files the user is authorized to use; credentials are never embedded in the Bible.
