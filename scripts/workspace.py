"""Keep production inputs, generated assets and financial state outside the Skill."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from common import CinemaError

SKILL_ROOT = Path(__file__).resolve().parents[1]


def ensure_external_project(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved.is_relative_to(SKILL_ROOT):
        raise CinemaError("Production files must be outside the Skill/repository; select a local projects directory")
    for parent in (resolved, *resolved.parents):
        if (parent / "SKILL.md").is_file() and (parent / "scripts/cinema.py").is_file():
            source = (parent / "SKILL.md").read_text(encoding="utf-8-sig")
            frontmatter = source.split("---", 2)
            if len(frontmatter) >= 3 and "name: cinematic-ai-studio" in frontmatter[1]:
                raise CinemaError("Production files must be outside every Cinematic AI Studio Skill copy")
    return resolved


def new_project_directory() -> Path:
    configured = os.environ.get("CINEMA_PROJECTS_DIR")
    base = Path(configured) if configured else Path.home() / "CinematicAIStudio" / "projects"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return ensure_external_project(base / f"production-{stamp}-{uuid4().hex[:8]}")
