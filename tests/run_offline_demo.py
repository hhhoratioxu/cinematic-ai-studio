"""Real media-processing proof using SYNTHETIC TEST PATTERNS, never a film sample."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audio_engine import AudioEngine, original_score, subtitles
from common import command, digest, media_tool, write_json
from editing_engine import export_episode, normalize_shot
from fonts import select_font
from image_engine import ImageEngine
from mock_provider import MockOpenAI
from models import Dialogue, Output, Plan, Settings, Shot
from quality_control import inspect_video, require_pass
from state import Ledger
from fixtures import generic_character


def run(directory: Path):
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    settings = Settings(lipsync="off", vision_qc=False,
                        ceilings_usd={"openai:image": 0.1, "openai:tts": 0.03})
    cast = [generic_character("actor_a", "cedar"), generic_character("actor_b", "marin")]
    shots = []
    for i, character in enumerate([cast[0], cast[1], cast[0]]):
        shots.append(Shot(id=f"test_s{i + 1:03d}", characters=[character.id], duration=2,
            subject="Synthetic test pattern, no actors", action="Abstract shapes change position every frame.",
            expression="not an acting test", environment="FFmpeg synthetic fixture", camera="medium",
            lighting="test pattern colors", temporal_motion="The pattern changes over the complete interval.",
            continuity="Synthetic fixture, no model generation", dialogue=[Dialogue(character=character.id,
            text=["测试字幕甲", "测试字幕乙", "测试结束"][i], start=0.25, end=1.5)]))
    output = select_font(Output(width=320, height=576, fps=24))
    plan = Plan(title="TEST ONLY — synthetic pipeline fixture", mode="anime", target_seconds=6,
                output=output, characters=cast, shots=shots)
    api = MockOpenAI()
    ledger = Ledger(directory / "test_tasks.sqlite3", 10, True)
    try:
        image = ImageEngine(settings, ledger, api).generate("Mock image workflow test", directory / "mock.png")
        audio = AudioEngine(settings, ledger, api)
        normalized, timings = [], {}
        sources = []
        for i, shot in enumerate(shots):
            raw = directory / f"TEST_PATTERN_{i}.mp4"
            command([media_tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                     "testsrc2=s=160x288:r=24", "-vf", f"hue=h={i * 50}", "-t", "2", "-an", "-c:v",
                     "libx264", "-pix_fmt", "yuv420p", str(raw)])
            require_pass(inspect_video(raw, settings, duration=2), shot.id)
            speech, timing = audio.dialogue(shot, cast, directory / shot.id)
            timings[shot.id] = timing
            cooked = directory / "normalized" / f"{shot.id}.mkv"
            normalize_shot(raw, speech, cooked, shot, output, settings)
            normalized.append(cooked)
            sources.append({"shot": shot.id, "sha256": digest(raw), "evidence": "synthetic_test_pattern"})
        edit = directory / "edit"
        edit.mkdir(exist_ok=True)
        subtitles(plan, edit, timings)
        music = original_score(directory / "original_test_music.wav", 6)
        final = export_episode(normalized, plan, edit, settings, music, test_only=True)
        qc = inspect_video(final, settings, 6, output, require_audio=True)
        require_pass(qc, "offline_pipeline")
        result = {"status": "offline_pipeline_pass", "test_only": True, "real_model_generation": False,
                  "real_Mandarin_speech": False, "audio": "mock tones, distinct voice IDs scheduled",
                  "output": str(final), "image_workflow": str(image), "shots": sources, "technical_qc": qc,
                  "paid_calls": 0, "actual_cost_usd": 0, "mock_calls": api.calls}
        write_json(directory / "TEST_ONLY_manifest.json", result)
        return result
    finally:
        ledger.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = run(args.out)
    print(json.dumps({k: result[k] for k in ("status", "output", "test_only", "paid_calls")}, ensure_ascii=False))
