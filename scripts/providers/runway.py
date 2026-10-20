"""Runway official v2024-11-06 API, checked 2026-10-20."""
from __future__ import annotations

import base64
from pathlib import Path

from common import CinemaError
from providers.base import HTTP, api_key


def image_uri(path: str) -> str:
    p = Path(path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    data = p.read_bytes()
    if len(data) > 3_500_000:
        raise CinemaError("Runway inline image exceeds 3.5 MB; export a smaller reference image")
    return f"data:{mime};base64," + base64.b64encode(data).decode()


class Runway:
    name = "runway"

    def __init__(self, client=None):
        self.http = HTTP("https://api.dev.runwayml.com", {
            "Authorization": "Bearer " + api_key("RUNWAYML_API_SECRET"),
            "X-Runway-Version": "2024-11-06"}, client)

    def validate(self, spec):
        model = spec["model"]
        if spec.get("kind") == "sfx":
            if model != "eleven_text_to_sound_v2" or not 0.5 <= spec["duration"] <= 30:
                raise CinemaError("Unsupported Runway sound model or duration")
            return
        if model not in ("gen4.5", "gen4_turbo", "veo3.1", "veo3.1_fast"):
            raise CinemaError(f"Runway model {model} is not in this adapter's verified capability set")
        if len(spec["prompt"].encode("utf-16-le")) // 2 > 1000:
            raise CinemaError("Runway prompt exceeds 1000 UTF-16 units; tighten the shot, never truncate actions")
        if spec.get("elements"):
            raise CinemaError("Selected Runway models do not accept Kling Element IDs")
        if model.startswith("veo"):
            if spec["duration"] not in (4, 6, 8):
                raise CinemaError("Runway Veo 3.1 requires 4, 6 or 8 seconds")
        else:
            if not 2 <= spec["duration"] <= 10:
                raise CinemaError("Runway Gen-4.5/Turbo requires 2-10 seconds")
            if spec.get("last_frame"):
                raise CinemaError("Gen-4.5/Turbo supports a first frame only; choose Veo 3.1 or Kling")
            if model == "gen4_turbo" and not spec.get("first_frame"):
                raise CinemaError("gen4_turbo requires a first frame")
        self.body(spec, inline=False)

    def body(self, spec, inline=True):
        if spec.get("kind") == "sfx":
            return "/v1/sound_effect", {"model": spec["model"], "promptText": spec["prompt"],
                                         "duration": spec["duration"], "loop": False}
        body = {"model": spec["model"], "promptText": spec["prompt"], "ratio": spec["ratio"],
                "duration": spec["duration"]}
        first = spec.get("first_frame")
        endpoint = "/v1/image_to_video" if first else "/v1/text_to_video"
        allowed = {"1280:720", "720:1280"}
        if first and not spec["model"].startswith("veo"):
            allowed |= {"1104:832", "960:960", "832:1104", "1584:672"}
        if spec["model"].startswith("veo"):
            allowed |= {"1080:1920", "1920:1080"}
            body["audio"] = spec.get("native_audio") == "preserve"
        if body["ratio"] not in allowed:
            raise CinemaError(f"Unsupported ratio for {spec['model']}: {body['ratio']}")
        if first:
            body["promptImage"] = [{"uri": image_uri(first) if inline else "preflight", "position": "first"}]
            if spec.get("last_frame"):
                body["promptImage"].append({"uri": image_uri(spec["last_frame"]) if inline else "preflight",
                                            "position": "last"})
        return endpoint, body

    def submit(self, spec, key):
        endpoint, body = self.body(spec)
        return self.http.request("POST", endpoint, json=body).json()["id"]

    def poll(self, task_id, spec):
        data = self.http.request("GET", "/v1/tasks/" + task_id).json()
        meta = {k: data[k] for k in ("cost", "estimatedCost", "status") if k in data}
        if data["status"] == "SUCCEEDED":
            if not data.get("output"):
                raise CinemaError("Runway succeeded without output; resume existing task")
            return {"state": "complete", "url": data["output"][0], "metadata": meta}
        if data["status"] in ("FAILED", "CANCELLED"):
            return {"state": "failed", "reason": data.get("failureCode", data["status"]), "metadata": meta}
        return {"state": "pending", "metadata": meta}
