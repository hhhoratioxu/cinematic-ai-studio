"""Package only reviewed skill content, with hashes and source revision provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from distribution_policy import audit_tracked, distribution_files
from install_skill import ROOT
from version import VERSION


def package(directory: Path):
    clean = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    if clean.returncode == 0 and clean.stdout.strip():
        raise RuntimeError("Commit reviewed source before packaging so the archive matches its source revision")
    directory.mkdir(parents=True, exist_ok=True)
    files = distribution_files(ROOT)
    audit_tracked(ROOT)
    archive = directory / f"cinematic-ai-studio-v{VERSION}.zip"
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
    provenance = {"version": VERSION, "archive": archive.name, "sha256": digest,
                  "source_commit": git.stdout.strip() if git.returncode == 0 else None,
                  "source_repository": "https://github.com/hhhoratioxu/cinematic-ai-studio",
                  "file_count": len(files), "real_provider_acceptance": "not_performed_no_keys_or_paid_authorization",
                  "paid_generation_calls": 0}
    provenance["acceptance"] = {"Offline Tested": "See validation.json", "Media Pipeline Verified": "See validation.json",
        "Provider Live Verified": "Pending", "Full Episode Rendered": "Pending", "Editorially Reviewed": "Pending"}
    (directory / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    print(json.dumps(package(parser.parse_args().out), indent=2))
