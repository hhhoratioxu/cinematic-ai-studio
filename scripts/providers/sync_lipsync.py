"""Sync's official multipart /v2/generate, using an existing dynamic video."""
from contextlib import ExitStack
from pathlib import Path

from common import CinemaError
from providers.base import HTTP, api_key


class SyncLipsync:
    name = "sync"

    def __init__(self, client=None):
        self.http = HTTP("https://api.sync.so", {"x-api-key": api_key("SYNC_API_KEY")}, client)

    def validate(self, spec):
        if spec["model"] not in ("lipsync-2", "lipsync-2-pro"):
            raise CinemaError("Unsupported Sync model")
        if not Path(spec["video"]).is_file() or not Path(spec["audio"]).is_file():
            raise CinemaError("Lip sync needs existing video and timed audio files")

    def submit(self, spec, key):
        with ExitStack() as stack:
            files = {name: (Path(spec[name]).name, stack.enter_context(Path(spec[name]).open("rb")), mime)
                     for name, mime in [("video", "video/mp4"), ("audio", "audio/wav")]}
            # No loop/retime mode: prepared audio already spans exactly the source shot.
            return self.http.request("POST", "/v2/generate", data={"model": spec["model"]}, files=files,
                                     headers={"Idempotency-Key": key}).json()["id"]

    def poll(self, task_id, spec):
        data = self.http.request("GET", "/v2/generate/" + task_id).json()
        if data["status"] == "COMPLETED":
            return {"state": "complete", "url": data["outputUrl"], "metadata": {"status": data["status"]}}
        if data["status"] in ("FAILED", "REJECTED"):
            return {"state": "failed", "reason": data.get("errorCode", data["status"])}
        return {"state": "pending"}
