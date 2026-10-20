"""Install a clean, self-contained skill into Codex's user skill directory."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ["SKILL.md", "agents", "references", "scripts", "assets", "tests",
           "requirements.txt", "requirements-dev.txt", "pyproject.toml", "README.md", "LICENSE"]


def install(destination: Path):
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}. Install to a new path or review it first.")
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("Install outside the source repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    for name in CONTENT:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, destination / name,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "*.part"))
        elif source.is_file():
            shutil.copy2(source, destination / name)
        else:
            raise FileNotFoundError(f"Missing release content: {source}")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path.home() / ".agents" / "skills" / "cinematic-ai-studio",
                        help="Defaults to ~/.agents/skills/cinematic-ai-studio; older hosts can use ~/.codex/skills")
    args = parser.parse_args()
    print(json.dumps({"installed": str(install(args.destination)), "paid_calls": 0,
                      "note": "Codex detects supported skill folders; restart if it is not visible."}))
