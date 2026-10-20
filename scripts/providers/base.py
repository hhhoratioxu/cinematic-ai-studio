from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from common import CinemaError, TaskFailed, UncertainSubmission, content_key
from state import Ledger


class ProviderError(CinemaError):
    def __init__(self, provider: str, status: int, uncertain: bool = False):
        self.status = status
        self.uncertain = uncertain
        super().__init__(f"{provider}: HTTP {status}; check provider access, quota and request capability")


def api_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CinemaError(f"Missing environment variable {name}")
    return value


class HTTP:
    def __init__(self, base: str, headers: dict, client: httpx.Client | None = None):
        self.base = base.rstrip("/")
        self.headers = headers
        self.client = client or httpx.Client(timeout=httpx.Timeout(300, connect=30), follow_redirects=False)

    def request(self, method: str, endpoint: str, **kwargs):
        try:
            r = self.client.request(method, self.base + endpoint,
                                    headers={**self.headers, **kwargs.pop("headers", {})}, **kwargs)
        except httpx.HTTPError as e:
            if method == "POST":
                raise UncertainSubmission("Submission outcome unknown; no automatic paid retry") from e
            raise CinemaError("Provider polling connection failed; resume the existing task") from e
        if not 200 <= r.status_code < 300:
            raise ProviderError(urlparse(self.base).hostname or "provider", r.status_code,
                                uncertain=method == "POST" and r.status_code >= 500)
        return r


def download(url: str, output: Path, client: httpx.Client | None = None, max_bytes=1024 * 1024 * 1024):
    """Separate unauthenticated client; resume only a matching byte range."""
    from workspace import ensure_external_project
    output = ensure_external_project(output)
    if urlparse(url).scheme != "https":
        raise CinemaError("Provider download must use HTTPS")
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_suffix(output.suffix + ".part")
    offset = part.stat().st_size if part.exists() else 0
    headers = {"Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    own = client is None
    client = client or httpx.Client(timeout=180, follow_redirects=False)
    try:
        for _ in range(6):
            with client.stream("GET", url, headers=headers) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    from urllib.parse import urljoin
                    url = urljoin(url, r.headers.get("location", ""))
                    if urlparse(url).scheme != "https":
                        raise CinemaError("Refusing insecure media redirect")
                    continue
                if r.status_code == 206:
                    if not r.headers.get("content-range", "").startswith(f"bytes {offset}-"):
                        raise CinemaError("Invalid download Content-Range; partial file retained")
                elif r.status_code == 200:
                    offset = 0
                else:
                    raise CinemaError(f"Media download HTTP {r.status_code}; resume to refresh task URL")
                size = offset
                with part.open("ab" if offset else "wb") as f:
                    for block in r.iter_bytes():
                        size += len(block)
                        if size > max_bytes:
                            raise CinemaError("Media download exceeds configured size limit")
                        f.write(block)
                    f.flush()
                    os.fsync(f.fileno())
                if not size:
                    raise CinemaError("Empty media download")
                os.replace(part, output)
                return
        raise CinemaError("Too many media redirects")
    except httpx.HTTPError as e:
        raise CinemaError("Download interrupted; partial bytes retained for resume") from e
    finally:
        if own:
            client.close()


class AsyncJobs:
    def __init__(self, ledger: Ledger, poll_seconds: float = 5, timeout: int = 1800,
                 sleep=time.sleep, downloader=download):
        self.ledger = ledger
        self.poll_seconds = poll_seconds
        self.timeout = timeout
        self.sleep = sleep
        self.downloader = downloader

    def run(self, provider, spec: dict, output: Path, ceiling: float, kind="video", attempt=0):
        # Validate capabilities and keys before reserving or initiating a paid action.
        provider.validate(spec)
        key = content_key({"provider": provider.name, "spec": spec, "kind": kind, "attempt": attempt})
        row = self.ledger.reserve(key, provider.name, kind, ceiling, spec, output)
        output = Path(row["output"])
        if self.ledger.cached(row):
            return output, key
        if row["state"] in ("submitting", "uncertain"):
            raise UncertainSubmission(f"Task {key} needs reconciliation; refusing duplicate submission")
        if row["state"] in ("failed", "rejected"):
            raise TaskFailed(f"Task {key} previously failed: {row['error']}")
        if row["state"] == "complete" and not row["task_id"]:
            raise CinemaError("Cached file was modified/missing and cannot be re-downloaded")
        if row["state"] == "reserved":
            self.ledger.update(key, state="submitting")
            try:
                task_id = provider.submit(spec, key)
                if not task_id:
                    raise UncertainSubmission("Provider accepted request without a task ID")
                self.ledger.update(key, state="submitted", task_id=str(task_id))
            except ProviderError as e:
                self.ledger.update(key, state="uncertain" if e.uncertain else "failed", error=str(e))
                if e.uncertain:
                    raise UncertainSubmission(f"Task {key}: response uncertain; reconcile before retry") from e
                raise TaskFailed(str(e)) from e
            except BaseException:
                self.ledger.update(key, state="uncertain", error="Submission interrupted; outcome unknown")
                raise
            row = self.ledger.get(key)
        started = time.monotonic()
        while True:
            status = provider.poll(row["task_id"], spec)
            self.ledger.update(key, metadata=json.dumps(status.get("metadata", {})))
            if status["state"] == "complete":
                self.downloader(status["url"], output)
                self.ledger.complete(key, output, status.get("metadata", {}))
                return output, key
            if status["state"] == "failed":
                reason = status.get("reason", "Provider task failed")
                self.ledger.update(key, state="failed", error=reason)
                raise TaskFailed(f"{provider.name} task {row['task_id']}: {reason}")
            if time.monotonic() - started >= self.timeout:
                raise CinemaError(f"Task {row['task_id']} still pending; use resume without resubmitting")
            self.sleep(self.poll_seconds)


class SyncJobs:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def run(self, provider: str, kind: str, spec: dict, output: Path, ceiling: float, action):
        key = content_key({"provider": provider, "kind": kind, "spec": spec})
        row = self.ledger.reserve(key, provider, kind, ceiling, spec, output)
        output = Path(row["output"])
        if self.ledger.cached(row):
            return output
        if row["state"] != "reserved":
            raise UncertainSubmission(f"{kind} {key}: cached response unavailable; reconcile before paying again")
        self.ledger.update(key, state="submitting")
        try:
            metadata = action(output) or {}
            self.ledger.complete(key, output, metadata)
        except ProviderError as e:
            self.ledger.update(key, state="uncertain" if e.uncertain else "failed", error=str(e))
            raise
        except BaseException:
            self.ledger.update(key, state="uncertain", error="Synchronous response unavailable")
            raise
        return output
