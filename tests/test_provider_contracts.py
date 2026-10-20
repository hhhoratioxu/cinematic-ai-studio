import base64
import json

import httpx
import pytest
from PIL import Image

from common import CinemaError
from providers.base import HTTP, ProviderError, download
from providers.kling import Kling, jwt_token
from providers.openai_api import OpenAI
from providers.runway import Runway
from providers.sync_lipsync import SyncLipsync


def test_runway_t2v_and_i2v_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNWAYML_API_SECRET", "test-secret")
    seen = []
    def handle(req):
        seen.append(req)
        return httpx.Response(200, json={"id": "task-1"})
    adapter = Runway(httpx.Client(transport=httpx.MockTransport(handle)))
    spec = {"model": "gen4.5", "prompt": "A woman walks forward, turns and smiles.", "ratio": "720:1280",
            "duration": 6}
    adapter.submit(spec, "key")
    assert seen[-1].url.path == "/v1/text_to_video"
    assert seen[-1].headers["X-Runway-Version"] == "2024-11-06"
    image = tmp_path / "first.png"
    Image.new("RGB", (320, 480)).save(image)
    spec["first_frame"] = str(image)
    adapter.submit(spec, "key")
    body = json.loads(seen[-1].content)
    assert seen[-1].url.path == "/v1/image_to_video"
    assert body["promptImage"][0]["position"] == "first"
    assert body["promptImage"][0]["uri"].startswith("data:image/png;base64,")
    assert "negative_prompt" not in body


def test_runway_rejects_unsupported_controls_before_submission(monkeypatch):
    monkeypatch.setenv("RUNWAYML_API_SECRET", "test")
    adapter = Runway()
    spec = {"model": "gen4.5", "prompt": "moves", "duration": 6, "ratio": "720:1280",
            "first_frame": "first.png", "last_frame": "last.png"}
    with pytest.raises(CinemaError, match="first frame only"):
        adapter.validate(spec)
    spec.pop("last_frame")
    spec["prompt"] = "😀" * 501
    with pytest.raises(CinemaError, match="UTF-16"):
        adapter.validate(spec)


def test_runway_veo_last_frame_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNWAYML_API_SECRET", "test")
    image = tmp_path / "f.png"
    Image.new("RGB", (320, 480)).save(image)
    adapter = Runway()
    spec = {"model": "veo3.1", "prompt": "continuous walking", "duration": 6,
            "ratio": "720:1280", "first_frame": str(image), "last_frame": str(image), "native_audio": "replace"}
    adapter.validate(spec)
    endpoint, body = adapter.body(spec)
    assert [p["position"] for p in body["promptImage"]] == ["first", "last"]
    assert body["audio"] is False


def test_kling_legacy_and_bearer_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("KLING_API_KEY", "test-api-key")
    image = tmp_path / "f.png"
    Image.new("RGB", (320, 480)).save(image)
    seen = []
    def handle(req):
        seen.append(req)
        return httpx.Response(200, json={"code": 0, "data": {"task_id": "kling-task"}})
    adapter = Kling(httpx.Client(transport=httpx.MockTransport(handle)))
    spec = {"model": "kling-v2-6", "prompt": "A man turns his head and walks.", "duration": 5,
            "aspect_ratio": "9:16", "first_frame": str(image), "last_frame": str(image)}
    assert adapter.submit(spec, "stable-task-key") == "kling-task"
    req = seen[-1]
    body = json.loads(req.content)
    assert str(req.url) == "https://api-singapore.klingai.com/v1/videos/image2video"
    assert req.headers["Authorization"] == "Bearer test-api-key"
    assert body["duration"] == "5" and body["sound"] == "off"
    assert body["external_task_id"] == "stable-task-key"
    assert not body["image"].startswith("data:")
    assert base64.b64decode(body["image"]) == image.read_bytes()


def test_kling_jwt_contract():
    token = jwt_token("access", "secret")
    header, payload, signature = token.split(".")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert data["iss"] == "access" and data["exp"] - data["nbf"] == 1805
    assert len(signature) == 43


def test_sync_uploads_actual_video_and_audio_with_idempotency(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNC_API_KEY", "test-sync")
    video, audio = tmp_path / "clip.mp4", tmp_path / "speech.wav"
    video.write_bytes(b"video-fixture")
    audio.write_bytes(b"audio-fixture")
    seen = []
    def handle(req):
        seen.append(req)
        return httpx.Response(201, json={"id": "sync-task", "status": "PENDING"})
    adapter = SyncLipsync(httpx.Client(transport=httpx.MockTransport(handle)))
    spec = {"model": "lipsync-2", "video": str(video), "audio": str(audio)}
    adapter.validate(spec)
    adapter.submit(spec, "stable-key")
    req = seen[-1]
    assert req.headers["Idempotency-Key"] == "stable-key"
    assert b"video-fixture" in req.content and b"audio-fixture" in req.content
    assert b"loop" not in req.content


def test_openai_image_and_reference_edit(monkeypatch, tmp_path):
    import io
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    b = io.BytesIO()
    Image.new("RGB", (16, 16)).save(b, format="PNG")
    seen = []
    def handle(req):
        seen.append(req)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b.getvalue()).decode()}]})
    api = OpenAI(httpx.Client(transport=httpx.MockTransport(handle)))
    image = tmp_path / "out.png"
    api.image("cinematic original character", image, "gpt-image-1.5", "1024x1536", "medium")
    assert seen[-1].url.path == "/v1/images/generations"
    assert "response_format" not in json.loads(seen[-1].content)
    api.image("turn to side", tmp_path / "side.png", "gpt-image-1.5", "1024x1536", "medium", [image])
    assert seen[-1].url.path == "/v1/images/edits"
    assert b'name="image[]"' in seen[-1].content


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_failure_never_leaks_body_or_key(status):
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, text="secret-value")))
    with pytest.raises(ProviderError) as error:
        HTTP("https://api.example.test", {"Authorization": "secret-key"}, client).request("POST", "/task", json={})
    assert "secret" not in str(error.value)
    assert error.value.uncertain == (status >= 500)


def test_download_resume_without_forwarding_provider_authorization(tmp_path):
    output = tmp_path / "video.mp4"
    output.with_suffix(".mp4.part").write_bytes(b"abc")
    def handle(req):
        assert req.headers["Range"] == "bytes=3-"
        assert "authorization" not in req.headers
        return httpx.Response(206, headers={"Content-Range": "bytes 3-5/6"}, content=b"def")
    download("https://cdn.example.test/video", output, httpx.Client(transport=httpx.MockTransport(handle)))
    assert output.read_bytes() == b"abcdef"


def test_download_rejects_wrong_range_and_http(tmp_path):
    output = tmp_path / "video.mp4"
    output.with_suffix(".mp4.part").write_bytes(b"abc")
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(
        206, headers={"Content-Range": "bytes 0-5/6"}, content=b"wrong")))
    with pytest.raises(CinemaError, match="Content-Range"):
        download("https://cdn.example.test/video", output, client)
    with pytest.raises(CinemaError, match="HTTPS"):
        download("http://cdn.example.test/video", output, client)
