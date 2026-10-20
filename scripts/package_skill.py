"""Package only reviewed skill content, with hashes and source revision provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from install_skill import CONTENT, ROOT


def package(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for name in CONTENT:
        source = ROOT / name
        files += sorted(p for p in source.rglob("*") if p.is_file()) if source.is_dir() else [source]
    files = [p for p in files if "__pycache__" not in p.parts and not p.name.endswith((".pyc", ".part"))]
    archive = directory / "cinematic-ai-studio-v0.1.0.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files):
            name = "cinematic-ai-studio/" + path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (directory / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    provenance = {"version": "0.1.0", "archive": archive.name, "sha256": digest,
                  "source_commit": git.stdout.strip() if git.returncode == 0 else None,
                  "source_repository": "https://github.com/hhhoratioxu/cinematic-ai-studio",
                  "file_count": len(files), "real_provider_acceptance": "not_performed_no_keys_or_paid_authorization",
                  "paid_generation_calls": 0}
    (directory / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    print(json.dumps(package(parser.parse_args().out), indent=2))
