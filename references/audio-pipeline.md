# Audio and timing

Each dialogue event has a Character ID, Simplified Chinese text, shot-relative start/end, delivery (`onscreen`, `offscreen`, `narration`) and emotional instruction. Built-in OpenAI voice IDs stay fixed in the Bible. The TTS request explicitly asks for Mandarin and emotion. Voices are synthetic; no voice cloning is implemented.

Version 2 includes stable character `speech_style` and intended `speech_speed` in TTS instructions; measured output still controls timeline fit. This is a requested speaking pace, not a guarantee of exact timing. Punctuation and text provide pauses. Both the raw take and fitted WAV remain on disk.

The engine measures returned WAV duration. It preserves short takes and permits at most a 1.20× tempo adjustment for a slightly long take. Longer speech stops with the exact shot/window; revise the script instead of chopping words or speeding speech drastically. Events cannot overlap or exceed the shot. The subtitle end uses the measured spoken take where available. WAVs, scheduled timing JSON, SRT and ASS remain on disk.

`native_audio=replace` removes generated native speech and adds the scheduled dub once. `preserve` keeps native audio once and skips new TTS/lip sync; any requested dialogue's exact words and timing then need audiovisual verification. `mute` is allowed for non-dialogue shots. Effects can be added under all three policies. An empty replacement track is real silence under moving footage, not fabricated dialogue.

With `lipsync=sync`, on-screen dubbed shots send existing generated moving footage and a full-length timed WAV to the official Sync model. This adapter supports one visible speaker per such shot. Use reverse shots to handle multiple characters. Offscreen narration does not trigger mouth generation. With `lipsync=off`, voice timing still works, but mouth-to-speech sync is unverified and must never be claimed as achieved.

Generated environment/action effects use Runway's official sound API and reserve separate costs. Alternatively supply a local `Sound.file` plus `license` rights declaration. Background music is an imported file with `music_license`, or an optional original procedural ambient chord bed. The built-in bed is explicitly identified as procedural music, not an AI-generated orchestral score. User-owned/licensed music can be looped in the audio mix; narrative video is never looped. Sidechain ducking lowers the music under dialogue.

The installed skill does not bundle proprietary fonts or music. Set `output.font_file` or `CINEMA_FONT` to a local licensed CJK font. Windows Microsoft YaHei, macOS PingFang and Linux Noto Sans CJK are discovered locally. Subtitle wrapping measures the selected font, restricts to two lines within 8% safe margins and neutralizes ASS layout overrides from dialogue. Review rendered glyphs and line breaks in the actual export.

Streams are normalized to 48 kHz stereo. Intermediate PCM audio avoids accumulating AAC padding between shots; AAC is encoded at final MP4 export. The final duration and audio/video stream start offsets are checked, but timestamps alone cannot verify facial phoneme synchronization.

Sound cues support fade-in/out. Version-2 music cues have timeline start/end, gains, rights and ramps; overlapping cues crossfade in the local bus before dialogue ducking. Shot `edit.audio_fade` applies short audio edge fades at picture cuts. Original generated and lip-synced videos, task IDs/hashes and separately reserved costs remain available. A static/uncertain raw shot requires exact-hash motion approval before a paid Sync request. Sample-peak readings flag possible clipping; true-peak compliance and perceptual mix/lip-sync remain audiovisual acceptance work.
