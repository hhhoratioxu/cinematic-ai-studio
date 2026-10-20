"""Small filesystem, content identity, and subprocess helpers."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class CinemaError(Exception):
    pass


class BudgetError(CinemaError):
    pass


class UncertainSubmission(CinemaError):
    pass


class TaskFailed(CinemaError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def content_key(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def atomic_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def media_tool(name: str, configured: str | None = None) -> str:
    candidate = configured or os.environ.get("CINEMA_" + name.upper()) or shutil.which(name)
    if not candidate and os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        matches = sorted((local / "Microsoft/WinGet/Packages").glob(f"Gyan.FFmpeg_*/ffmpeg-*/bin/{name}.exe"))
        candidate = str(matches[-1]) if matches else None
    if not candidate:
        raise CinemaError(f"{name} unavailable; install FFmpeg or set CINEMA_{name.upper()}")
    if not Path(candidate).is_file() and not shutil.which(candidate):
        raise CinemaError(f"Configured {name} executable does not exist")
    return str(candidate)


def command(args: list[str], timeout: int = 1800, cwd: Path | None = None):
    try:
        result = subprocess.run([str(x) for x in args], capture_output=True, timeout=timeout,
                                cwd=cwd, encoding="utf-8", errors="replace", check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CinemaError(f"Media tool failed: {type(e).__name__}") from e
    if result.returncode:
        raise CinemaError(f"{Path(args[0]).name} failed: {result.stderr[-3000:]}")
    return result


def resolve_asset(value: str, base: Path) -> Path:
    p = Path(value).expanduser()
    p = p if p.is_absolute() else base / p
    if not p.is_file():
        raise CinemaError(f"Missing input asset: {p}")
    return p.resolve()
