"""Official OpenAI Images, Speech, and Responses HTTP adapters."""
from __future__ import annotations

import base64
import json
from contextlib import ExitStack
from pathlib import Path

from common import CinemaError, atomic_bytes, write_json
from providers.base import HTTP, api_key


class OpenAI:
    name = "openai"

    def __init__(self, client=None):
        self.http = HTTP("https://api.openai.com", {"Authorization": "Bearer " + api_key("OPENAI_API_KEY")},
                         client)

    def image(self, prompt, output: Path, model, size, quality, references=()):
        data = {"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1,
                "output_format": "png"}
        if references:
            with ExitStack() as stack:
                files = [("image[]", (p.name, stack.enter_context(p.open("rb")),
                                       "image/png" if p.suffix.lower() == ".png" else "image/jpeg"))
                         for p in references]
                if model == "gpt-image-1.5":
                    data["input_fidelity"] = "high"
                response = self.http.request("POST", "/v1/images/edits", data=data, files=files).json()
        else:
            response = self.http.request("POST", "/v1/images/generations", json=data).json()
        image = response.get("data", [{}])[0].get("b64_json")
        if not image:
            raise CinemaError("OpenAI Images returned no image bytes")
        atomic_bytes(output, base64.b64decode(image, validate=True))
        from PIL import Image
        with Image.open(output) as im:
            im.verify()
        return {"model": model, "usage": response.get("usage"), "evidence": "real_api_response"}

    def speech(self, text, voice, instructions, output: Path, model="gpt-4o-mini-tts"):
        voices = {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage",
                  "shimmer", "verse", "marin", "cedar"}
        if voice not in voices:
            raise CinemaError(f"Voice {voice} is not a supported built-in OpenAI voice")
        response = self.http.request("POST", "/v1/audio/speech", json={
            "model": model, "input": text, "voice": voice, "instructions": instructions,
            "response_format": "wav"})
        atomic_bytes(output, response.content)
        return {"model": model, "voice": voice, "evidence": "real_api_response"}

    def response_json(self, prompt, output: Path, model, images=(), max_tokens=16000):
        content = [{"type": "input_text", "text": prompt}]
        for p in images:
            mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            content.append({"type": "input_image", "image_url": "data:" + mime + ";base64," +
                            base64.b64encode(p.read_bytes()).decode()})
        data = self.http.request("POST", "/v1/responses", json={
            "model": model, "store": False, "input": [{"role": "user", "content": content}],
            "max_output_tokens": max_tokens, "text": {"format": {"type": "json_object"}}}).json()
        if data.get("status") != "completed":
            raise CinemaError("OpenAI planning/vision response incomplete; no production plan accepted")
        text = "".join(c.get("text", "") for item in data.get("output", [])
                       for c in item.get("content", []) if c.get("type") == "output_text")
        result = json.loads(text)
        write_json(output, result)
        return {"model": model, "usage": data.get("usage"), "response_id": data.get("id")}
