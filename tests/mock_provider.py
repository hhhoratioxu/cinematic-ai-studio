"""Test fixtures, never selected by production config and never real model evidence."""
import array
import math
import wave

from PIL import Image


class MockOpenAI:
    def __init__(self):
        self.calls = []

    def image(self, prompt, output, model, size, quality, references=()):
        self.calls.append({"kind": "image", "prompt": prompt, "references": list(references)})
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 480), (40 + len(self.calls) % 100, 80, 130)).save(output)
        return {"evidence": "mock_image", "actual_cost_usd": 0}

    def speech(self, text, voice, instructions, output, model="gpt-4o-mini-tts"):
        self.calls.append({"kind": "tts", "text": text, "voice": voice, "instructions": instructions})
        sr = 24000
        frequency = 220 if voice == "cedar" else 330
        data = array.array("h", [int(4000 * math.sin(2 * math.pi * frequency * i / sr))
                                 for i in range(sr // 2)])
        if __import__("sys").byteorder != "little":
            data.byteswap()
        with wave.open(str(output), "wb") as f:
            f.setparams((1, 2, sr, 0, "NONE", "not compressed"))
            f.writeframes(data.tobytes())
        return {"evidence": "mock_tone_not_speech", "actual_cost_usd": 0}


class MockVideo:
    name = "runway"
    evidence = "synthetic_test_fixture"

    def __init__(self, states=None):
        self.submissions = 0
        self.polls = 0
        self.specs = []
        self.states = list(states or ["complete"])

    def validate(self, spec):
        pass

    def submit(self, spec, key):
        self.submissions += 1
        self.specs.append(dict(spec))
        return "mock-" + key[:12]

    def poll(self, task_id, spec):
        self.polls += 1
        state = self.states.pop(0) if self.states else "complete"
        return {"state": state, "url": "https://fixture.invalid/video.mp4", "reason": "mock_failure"}
