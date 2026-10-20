"""Validate generic Skill metadata, reusable assets and synthetic test coverage."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import yaml

from distribution_policy import ASSETS, audit_tracked, distribution_files
from fixtures import generic_plan
from models import Character, Settings, read_model
from video_engine import validate_video_plan


def validate(root):
    source = (root / "SKILL.md").read_text(encoding="utf-8")
    assert source.startswith("---\n")
    front = yaml.safe_load(source.split("---", 2)[1])
    assert front["name"] == "cinematic-ai-studio"
    assert isinstance(front["description"], str) and "real video-generation models" in front["description"]
    interface = yaml.safe_load((root / "agents/openai.yaml").read_text(encoding="utf-8"))
    assert "$cinematic-ai-studio" in interface["interface"]["default_prompt"]
    assert interface["policy"]["allow_implicit_invocation"] is True
    for doc in [root / "SKILL.md", root / "README.md", *sorted((root / "references").glob("*.md"))]:
        prose = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.S)
        for link in re.findall(r"\]\(([^)]+)\)", prose):
            if "://" not in link and not link.startswith("#"):
                assert (doc.parent / link.split("#")[0]).exists(), f"Missing link {doc}: {link}"
    files = distribution_files(root)
    audit = audit_tracked(root)
    assert {p.name for p in (root / "assets").iterdir() if p.is_file()} == ASSETS
    characters = [Character.model_validate(c) for c in json.loads((root / "assets/characters.example.json").read_text(encoding="utf-8"))]
    assert characters and all(not c.story_state and not c.relationships and not c.references for c in characters)
    plan = generic_plan()
    assert plan.target_seconds == 180 and len(plan.shots) == 30
    assert len(plan.characters) == 3 and all(c.references == {} for c in plan.characters)
    assert sum(shot.duration for shot in plan.shots) == 180
    settings = read_model(root / "assets/config.example.json", Settings)
    checks = validate_video_plan(plan, settings, require_keys=False)
    assert len(checks) == 30
    return {"valid": True, "skill": front["name"], "fixture_shots": len(plan.shots),
            "fixture_seconds": plan.target_seconds, "fixture_is_default_project": False,
            "release_file_count": len(files), **audit, "paid_calls": 0}


if __name__ == "__main__":
    print(json.dumps(validate(Path(__file__).resolve().parents[1])))
