"""Install a clean, self-contained skill into Codex's user skill directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from common import content_key
from distribution_policy import distribution_files

ROOT = Path(__file__).resolve().parents[1]


def file_hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts and
            ".pytest_cache" not in p.parts and p.name != ".install-manifest.json" and not p.name.endswith(".pyc")}


def install(destination: Path, upgrade=False):
    destination = destination.expanduser().resolve()
    if destination.exists() and not upgrade:
        raise FileExistsError(f"Destination already exists: {destination}. Install to a new path or review it first.")
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("Install outside the source repository")
    files = distribution_files(ROOT)
    backup = None
    if destination.exists():
        if destination.is_symlink() or getattr(destination, "is_junction", lambda: False)():
            raise ValueError("Refusing to replace a linked skill directory")
        manifest = destination / ".install-manifest.json"
        if manifest.is_file():
            expected = json.loads(manifest.read_text(encoding="utf-8"))["files"]
            recognized = file_hashes(destination) == expected
        else:
            legacy = ROOT / "assets" / "legacy-install-fingerprints.json"
            fingerprints = json.loads(legacy.read_text(encoding="utf-8")) if legacy.is_file() else {}
            recognized = content_key(file_hashes(destination)) in fingerprints.values()
        if not recognized:
            raise ValueError("Existing skill contains unrecognized/user-modified files; preserve and review before upgrading")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = destination.parent.parent / "skill-backups" / f"{destination.name}-{stamp}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        # Move only the verified absolute skill root; never recurse through a computed parent.
        destination.rename(backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    try:
        for source in files:
            target = destination / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        from version import VERSION
        (destination / ".install-manifest.json").write_text(json.dumps(
            {"version": VERSION, "backup": str(backup) if backup else None, "files": file_hashes(destination)},
            indent=2) + "\n", encoding="utf-8")
    except BaseException:
        # Preserve partial output for inspection. Restore the prior installation atomically.
        if backup:
            destination.rename(destination.with_name(destination.name + "-failed-" + stamp))
            backup.rename(destination)
        raise
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path.home() / ".agents" / "skills" / "cinematic-ai-studio",
                        help="Defaults to ~/.agents/skills/cinematic-ai-studio; older hosts can use ~/.codex/skills")
    parser.add_argument("--upgrade", action="store_true", help="Back up and replace a verified managed installation")
    args = parser.parse_args()
    print(json.dumps({"installed": str(install(args.destination, args.upgrade)), "paid_calls": 0,
                      "note": "Codex detects supported skill folders; restart if it is not visible."}))
