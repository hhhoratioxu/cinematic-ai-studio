from __future__ import annotations

import socket

import pytest

from common import command, media_tool
from models import Plan, Settings, Shot
from fixtures import generic_character


@pytest.fixture(autouse=True)
def no_network_or_real_keys(monkeypatch):
    for key in ("OPENAI_API_KEY", "RUNWAYML_API_SECRET", "KLING_API_KEY", "KLING_ACCESS_KEY",
                "KLING_SECRET_KEY", "SYNC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    def deny(*args, **kwargs):
        raise AssertionError("Offline tests forbid real network connections")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


@pytest.fixture
def settings():
    return Settings(ceilings_usd={"openai:image": 0.1, "openai:tts": 0.03, "openai:planner": 0.1,
        "openai:vision": 0.02, "runway:video:gen4.5": 0.1, "kling:video:kling-v2-6": 0.1,
        "sync:lipsync": 0.1, "runway:sfx": 0.01}, lipsync="off", vision_qc=False, max_concurrency=2)


@pytest.fixture
def character():
    return generic_character()


@pytest.fixture
def shot(character):
    return Shot(id="s001", characters=[character.id], duration=2, subject="Synthetic calibration subject",
        action="The test subject raises a hand, turns toward a mark, then lowers the hand.",
        expression="neutral test expression", environment="plain calibration grid", camera="medium",
        lighting="neutral test fill", temporal_motion="First raise a hand, then turn, finally lower the hand.",
        continuity="Same calibration grid and neutral outfit")


@pytest.fixture
def plan(character, shot):
    return Plan(title="测试剧集", target_seconds=2, characters=[character], shots=[shot])


@pytest.fixture(scope="session")
def media_factory(tmp_path_factory):
    directory = tmp_path_factory.mktemp("moving-fixtures")
    try:
        ffmpeg = media_tool("ffmpeg")
        media_tool("ffprobe")
    except Exception as exc:
        pytest.fail(f"FFmpeg and FFprobe are required for the offline acceptance suite: {exc}")
    def create(name="moving", seconds=2, color=0, frozen=False, black=False):
        path = directory / f"{name}_{seconds}_{color}_{frozen}_{black}.mp4"
        if path.exists():
            return path
        source = "color=c=black:s=160x288:r=24" if black else (
            "color=c=blue:s=160x288:r=24" if frozen else "testsrc2=s=160x288:r=24")
        args = [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", source, "-t", str(seconds)]
        if color:
            args += ["-vf", f"hue=h={color}"]
        command(args + ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
        return path
    return create
