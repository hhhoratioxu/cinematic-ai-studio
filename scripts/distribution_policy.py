"""An allowlist for reusable Skill releases, independent of git-ignore state."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

CONTENT = ["SKILL.md", "agents", "references", "scripts", "assets", "tests", ".gitignore",
           "requirements.txt", "requirements-dev.txt", "pyproject.toml", "README.md", "CHANGELOG.md", "LICENSE"]
ASSETS = {"characters.example.json", "config.example.json", "studio.html", "legacy-install-fingerprints.json"}
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
ROOT_FILES = {name for name in CONTENT if "." in name or name == "LICENSE"}


def approved(relative: Path) -> bool:
    parts = relative.parts
    if len(parts) == 1:
        return relative.name in ROOT_FILES
    if parts[0] == "assets":
        return len(parts) == 2 and parts[1] in ASSETS
    if parts[0] == "agents":
        return parts == ("agents", "openai.yaml")
    if parts[0] == "references":
        return len(parts) == 2 and relative.suffix == ".md"
    if parts[0] in ("scripts", "tests"):
        return relative.suffix == ".py" and not any(p.startswith(".") for p in parts)
    return relative.as_posix() == ".github/workflows/ci.yml"


def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def distribution_files(root: Path) -> list[Path]:
    root = root.resolve()
    files = []
    for name in CONTENT:
        source = root / name
        if not source.exists() or linked(source):
            raise ValueError(f"Missing or linked release input: {name}")
        candidates = [source] if source.is_file() else []
        if source.is_dir():
            for current, dirs, names in os.walk(source, followlinks=False):
                for entry in [*dirs, *names]:
                    p = Path(current) / entry
                    if linked(p):
                        raise ValueError(f"Linked release input: {p.relative_to(root)}")
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                candidates.extend(Path(current) / n for n in names if not n.endswith((".pyc", ".part")))
        for path in candidates:
            relative = path.relative_to(root)
            if not approved(relative):
                raise ValueError(f"Unapproved release input: {relative}; keep production files in an external project")
            files.append(path)
    return sorted(files)


def audit_tracked(root: Path):
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if result.returncode or Path(result.stdout.strip()).resolve() != root.resolve():
        return {"git_tracked_audit": "not a repository checkout"}
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    names = [Path(n.decode("utf-8")) for n in result.stdout.split(b"\0") if n]
    bad = [p.as_posix() for p in names if (root / p).exists() and not approved(p)]
    if bad:
        raise ValueError("Unapproved tracked content: " + ", ".join(bad))
    return {"git_tracked_audit": "passed", "tracked_files": len(names)}
