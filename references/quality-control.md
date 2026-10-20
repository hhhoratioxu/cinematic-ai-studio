# Quality gates and evidence

The pipeline checks source clips before accepting a shot and checks the final MP4 again. Reports retain exact file hashes and the shot/task that produced each source.

| Check | Actual behavior | Limit |
|---|---|---|
| Decode | FFmpeg `-xerror` full decode | Decodability is not visual quality |
| Runtime | FFprobe against requested runtime | Frame/timebase tolerance up to 0.12 s or two frames |
| Size / ratio / fps | Exact configured size, fps and H.264/AAC on final export | May be explicitly post-upscaled |
| Audio | Required track, stream start offsets | Does not prove speech content or lip sync |
| Black / freeze | FFmpeg blackdetect and freezedetect, including an unfinished freeze at EOF | Dark intentional scenes or a deliberate held pose can require editorial review |
| Missing shots | Plan-to-accepted-source coverage | Does not judge plot quality |
| Repeated footage | Per-shot decoded low-resolution frame MD5 sequence | Exact decoded duplicates; near duplicates may escape |
| Sampled motion | LK optical flow, RANSAC camera compensation, subject/center residuals, repeated samples, temporal thirds, cut/flash triage | Sampled evidence, false positives/negatives; ambiguous and intentional holds need review |
| Continuity plan | Scene and input/output state changes with explicit reasons | Validates declared plans, cannot observe actual wardrobe/props/eyelines |
| Manual review | Current-source SHA-256, reviewer, observation and approve/reject history | Human judgement; new bytes invalidate the old decision |
| Character / action / anatomy | Default paid vision review of references and three chronological frames | Probabilistic sparse sampling; false positives/negatives possible |
| Subtitles | Window bounds, selected-font measured two-line layout and safe margins | Real rendered glyph bounds still need visual review |
| API failures | Persistent failed/uncertain task states and bounded shot attempts | Never refund a reserved amount without billing evidence |

Technical failure names the shot and stops or uses only its next configured attempt. Sparse-frame severe issues can reject a shot; do not claim the visual model proves a whole performance is flawless. Transport uncertainty is a recovery problem, not permission for a second paid submission. Budget checks apply before every new paid operation, including retry, planning, image, TTS, vision, sound and lip sync.

`manifest.json` is `incomplete` after failure and `rendered_requires_editorial_review` only after all technical checks and shot coverage pass. It never calls a technically valid film cinematographically certified. A production executor rejects synthetic/mock provenance. Offline test exports use `TEST_ONLY_` names, `test_only=true`, `real_model_generation=false` and `paid_calls=0`.

Run `python -m pytest -q` for offline A–H tests. Run `python tests/run_offline_demo.py --out SOME_TEST_DIRECTORY` for a reviewable six-second media-processing fixture. Its images are synthetic patterns and its mock voices are tones, not Chinese speech. It provides evidence for scheduling, encoding, subtitles and QC, not human motion, model availability, character identity, actual Mandarin quality or lip-sync effectiveness. Full provider acceptance requires credentials, budget and editorial review of generated footage; record those results separately.
