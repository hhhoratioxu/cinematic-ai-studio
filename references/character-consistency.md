# Character Bible

`characters.json` is an array of validated Character objects. Use `schema character` for the full contract. Fix Character ID, name, age, face, hair, height/build, wardrobe/accessories, temperament, voice, visual style and view references. Generated views are `front`, `side`, `full_body`; imported views are resolved relative to their JSON source.

The engine creates a front reference first and uses it as an edit reference for later views. Scene first frames use the corresponding front references and identity descriptions. Video requests include the scene first frame and identity prompt. Kling 3 can additionally consume existing authorized Element IDs. Text-only shots retain identity text but have weaker visual anchoring, which must be disclosed when selected for recurring characters.

Keep the same project Bible for subsequent episodes. Pass `--bible PREVIOUS_RUN/characters.json` alongside a new episode plan. Reused IDs reject changed face, hair, build, wardrobe, voice or style. A deliberate costume change can be modeled as a new versioned Character ID while retaining the original person's reference in the new design process; do not silently overwrite the previous Bible.

Character conditioning is a request to the model, not proof of continuity. Inspect first/middle/last frames against references and review the whole shot. Optional paid vision checks flag identity/anatomy/action concerns with sparse-frame uncertainty. A full visual review remains necessary before claiming the actor is consistent throughout the film.

Cache keys include generation settings, prompts and reference content hashes. Keep generated images and the task ledger together. Imported images, music and effects must be files the user is authorized to use; credentials are never embedded in the Bible.
