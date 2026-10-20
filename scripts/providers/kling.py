"""Kling official legacy API (still supported), Singapore endpoint, 2026-10-20."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from common import CinemaError
from providers.base import HTTP, api_key


def jwt_token(access: str, secret: str):
    def enc(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    header = enc(b'{"alg":"HS256","typ":"JWT"}')
    now = int(time.time())
    payload = enc(json.dumps({"iss": access, "exp": now + 1800, "nbf": now - 5}).encode())
    message = f"{header}.{payload}"
    return message + "." + enc(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest())


def raw_image(path):
    data = Path(path).read_bytes()
    if len(data) > 10 * 1024 * 1024:
        raise CinemaError("Kling reference image exceeds 10 MB")
    return base64.b64encode(data).decode()


class Kling:
    name = "kling"

    def __init__(self, client=None):
        self.http = HTTP("https://api-singapore.klingai.com", {}, client)
        self.auth()

    def auth(self):
        token = os.environ.get("KLING_API_KEY")
        if not token:
            token = jwt_token(api_key("KLING_ACCESS_KEY"), api_key("KLING_SECRET_KEY"))
        self.http.headers["Authorization"] = "Bearer " + token

    def validate(self, spec):
        if spec["model"] not in ("kling-v2-6", "kling-v3"):
            raise CinemaError("Kling adapter supports verified kling-v2-6 / kling-v3 legacy contracts")
        if len(spec["prompt"]) > 2500:
            raise CinemaError("Kling prompt exceeds 2500 characters")
        if spec["model"] == "kling-v2-6" and spec["duration"] not in (5, 10):
            raise CinemaError("Kling 2.6 shots require 5 or 10 seconds")
        if spec["model"] == "kling-v3" and not 3 <= spec["duration"] <= 10:
            raise CinemaError("Kling 3 shots in this pipeline require 3-10 seconds")
        if spec.get("elements") and (spec["model"] != "kling-v3" or not spec.get("first_frame")):
            raise CinemaError("Element references are enabled only for Kling 3 image-to-video")
        if len(spec.get("elements", [])) > 3 or any(not x.isdigit() for x in spec.get("elements", [])):
            raise CinemaError("Kling requires up to 3 numeric Element IDs from your element library")

    def body(self, spec, key):
        body = {"model_name": spec["model"], "prompt": spec["prompt"],
                "duration": str(spec["duration"]), "mode": spec.get("mode", "pro"),
                "sound": "on" if spec.get("native_audio") == "preserve" else "off",
                "external_task_id": key}
        if spec.get("first_frame"):
            endpoint = "/v1/videos/image2video"
            body["image"] = raw_image(spec["first_frame"])
            if spec.get("last_frame"):
                body["image_tail"] = raw_image(spec["last_frame"])
            if spec.get("elements"):
                body["element_list"] = [{"element_id": int(x)} for x in spec["elements"]]
        else:
            endpoint = "/v1/videos/text2video"
            body["aspect_ratio"] = spec["aspect_ratio"]
        return endpoint, body

    def submit(self, spec, key):
        self.auth()
        endpoint, body = self.body(spec, key)
        data = self.http.request("POST", endpoint, json=body).json()
        if data.get("code") != 0:
            raise CinemaError(f"Kling API rejected request with code {data.get('code')}")
        return data["data"]["task_id"]

    def poll(self, task_id, spec):
        self.auth()
        endpoint = "/v1/videos/image2video/" if spec.get("first_frame") else "/v1/videos/text2video/"
        result = self.http.request("GET", endpoint + task_id).json()
        if result.get("code") != 0:
            raise CinemaError(f"Kling query code {result.get('code')}; retain task and resume")
        data = result["data"]
        meta = {k: data[k] for k in ("task_status", "final_unit_deduction", "final_balance_deduction") if k in data}
        if data["task_status"] == "succeed":
            return {"state": "complete", "url": data["task_result"]["videos"][0]["url"], "metadata": meta}
        if data["task_status"] == "failed":
            return {"state": "failed", "reason": "Kling generation failed; inspect task in provider console",
                    "metadata": meta}
        return {"state": "pending", "metadata": meta}
