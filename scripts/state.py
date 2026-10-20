"""Durable task ledger. A pending/uncertain POST is never submitted twice."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from common import BudgetError, CinemaError, digest


def micros(value: float | str) -> int:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise BudgetError("Budget must be a nonnegative finite USD amount")
    return int((amount * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


class Ledger:
    def __init__(self, path: Path, budget: float, authorized: bool):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
                key TEXT PRIMARY KEY, provider TEXT NOT NULL, kind TEXT NOT NULL,
                ceiling INTEGER NOT NULL, state TEXT NOT NULL, task_id TEXT,
                output TEXT NOT NULL, sha256 TEXT, payload TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}', error TEXT,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        self.db.commit()
        self.budget = micros(budget)
        self.authorized = authorized
        with self.transaction():
            row = self.db.execute("SELECT value FROM meta WHERE key='budget'").fetchone()
            if row and int(row[0]) != self.budget:
                raise BudgetError("Resume with the original budget; use a new run for a new authorization")
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('budget', ?)", (str(self.budget),))

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def bind(self, key: str, value: str):
        with self.transaction():
            row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if row and row[0] != value:
                raise CinemaError(f"Run {key} changed; use a new output directory")
            self.db.execute("INSERT OR IGNORE INTO meta VALUES (?, ?)", (key, value))

    def get(self, key: str) -> dict | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM tasks WHERE key=?", (key,)).fetchone()
            return dict(row) if row else None

    def reserve(self, key: str, provider: str, kind: str, ceiling: float, payload: dict, output: Path):
        amount = micros(ceiling)
        with self.transaction():
            row = self.db.execute("SELECT * FROM tasks WHERE key=?", (key,)).fetchone()
            if row:
                return dict(row)
            if not self.authorized:
                raise BudgetError("Paid generation requires --allow-paid and an explicit --budget-usd")
            used = self.db.execute("SELECT COALESCE(SUM(ceiling),0) FROM tasks").fetchone()[0]
            if amount <= 0 or used + amount > self.budget:
                raise BudgetError(f"Budget stop: reserved ${used / 1e6:.4f}, next ${amount / 1e6:.4f}, "
                                  f"authorized ${self.budget / 1e6:.4f}")
            self.db.execute("INSERT INTO tasks (key,provider,kind,ceiling,state,output,payload) "
                            "VALUES (?,?,?,?,?,?,?)", (key, provider, kind, amount, "reserved",
                                                       str(output.resolve()), json.dumps(payload)))
        return self.get(key)

    def update(self, key: str, **fields):
        allowed = {"state", "task_id", "sha256", "metadata", "error"}
        if not fields or not set(fields) <= allowed:
            raise ValueError("invalid ledger update")
        with self.transaction():
            self.db.execute("UPDATE tasks SET " + ",".join(f"{k}=?" for k in fields) + " WHERE key=?",
                            (*fields.values(), key))

    def complete(self, key: str, output: Path, metadata: dict | None = None):
        self.update(key, state="complete", sha256=digest(output), metadata=json.dumps(metadata or {}))

    def cached(self, row: dict) -> bool:
        p = Path(row["output"])
        return row["state"] == "complete" and p.is_file() and digest(p) == row["sha256"]

    def summary(self):
        with self.lock:
            rows = [dict(r) for r in self.db.execute(
                "SELECT key,provider,kind,ceiling,state,task_id,metadata,error FROM tasks ORDER BY created,key")]
        return {"budget_usd": self.budget / 1e6,
                "reserved_ceiling_usd": sum(r.pop("ceiling") for r in rows) / 1e6,
                "actual_billed_usd": None,
                "billing_note": "Reservations are user-configured ceilings, not an invoice. "
                                "Failed and uncertain submissions retain their reservation.", "tasks": rows}

    def close(self):
        self.db.close()


@contextmanager
def run_lock(directory: Path):
    """OS releases lock on process death; no stale sentinel requiring unsafe deletion."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".run.lock").open("a+b") as f:
        f.seek(0)
        f.write(b"0")
        f.flush()
        f.seek(0)
        try:
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise CinemaError("Another process is using this output directory") from e
        try:
            yield
        finally:
            f.seek(0)
            if __import__("os").name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_UN)
