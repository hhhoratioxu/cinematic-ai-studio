from concurrent.futures import ThreadPoolExecutor

import pytest

from common import BudgetError, CinemaError, TaskFailed, UncertainSubmission
from mock_provider import MockVideo
from providers.base import AsyncJobs, SyncJobs
from state import Ledger, run_lock


def test_budget_is_atomic_across_workers(tmp_path):
    ledger = Ledger(tmp_path / "state.db", 1.0, True)
    def reserve(i):
        try:
            ledger.reserve(str(i), "test", "video", 0.6, {}, tmp_path / f"{i}.mp4")
            return True
        except BudgetError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reserve, range(2))) == 1
    assert ledger.summary()["reserved_ceiling_usd"] == 0.6
    ledger.close()


@pytest.mark.parametrize("budget", ["NaN", "Infinity", "-1"])
def test_bad_budget_rejected(tmp_path, budget):
    with pytest.raises(BudgetError):
        Ledger(tmp_path / "state.db", budget, True)


def test_no_paid_authorization_no_submission(tmp_path):
    ledger = Ledger(tmp_path / "state.db", 10, False)
    provider = MockVideo()
    with pytest.raises(BudgetError):
        AsyncJobs(ledger).run(provider, {}, tmp_path / "video.mp4", 1)
    assert provider.submissions == 0
    ledger.close()


def test_resume_queries_existing_task_without_rebuy(tmp_path):
    path = tmp_path / "state.db"
    ledger = Ledger(path, 10, True)
    provider = MockVideo(states=["pending", "complete"])
    def interrupt(_):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        AsyncJobs(ledger, sleep=interrupt).run(provider, {"shot": "s1"}, tmp_path / "clip.mp4", 1)
    ledger.close()
    reopened = Ledger(path, 10, True)
    downloads = []
    def copy(url, output):
        downloads.append(url)
        output.write_bytes(b"mock-video-bytes")
    jobs = AsyncJobs(reopened, downloader=copy)
    output, key = jobs.run(provider, {"shot": "s1"}, tmp_path / "clip.mp4", 1)
    assert output.read_bytes() == b"mock-video-bytes"
    jobs.run(provider, {"shot": "s1"}, tmp_path / "other-path.mp4", 1)
    assert provider.submissions == 1
    assert len(downloads) == 1
    assert reopened.summary()["reserved_ceiling_usd"] == 1
    reopened.close()


def test_ambiguous_post_must_not_retry(tmp_path):
    ledger = Ledger(tmp_path / "state.db", 10, True)
    class Interrupted(MockVideo):
        def submit(self, spec, key):
            self.submissions += 1
            raise UncertainSubmission("lost POST response")
    provider = Interrupted()
    for _ in range(2):
        with pytest.raises(UncertainSubmission):
            AsyncJobs(ledger).run(provider, {}, tmp_path / "clip.mp4", 1)
    assert provider.submissions == 1
    assert ledger.summary()["tasks"][0]["state"] == "uncertain"
    ledger.close()


def test_failed_tasks_retain_cost_and_need_new_bounded_attempt(tmp_path):
    ledger = Ledger(tmp_path / "state.db", 2, True)
    provider = MockVideo(states=["failed"])
    jobs = AsyncJobs(ledger)
    for _ in range(2):
        with pytest.raises(TaskFailed):
            jobs.run(provider, {}, tmp_path / "clip.mp4", 1)
    assert provider.submissions == 1
    assert ledger.summary()["reserved_ceiling_usd"] == 1
    ledger.close()


def test_cached_file_damage_redownloads_not_regenerates(tmp_path):
    ledger = Ledger(tmp_path / "state.db", 5, True)
    provider = MockVideo()
    def download(url, output):
        output.write_bytes(b"original")
    jobs = AsyncJobs(ledger, downloader=download)
    output, _ = jobs.run(provider, {}, tmp_path / "v.mp4", 1)
    output.write_bytes(b"corrupt")
    jobs.run(provider, {}, tmp_path / "v.mp4", 1)
    assert output.read_bytes() == b"original"
    assert provider.submissions == 1
    ledger.close()


def test_sync_crash_does_not_rebuy(tmp_path):
    ledger = Ledger(tmp_path / "state.db", 5, True)
    calls = []
    def fail(path):
        calls.append(path)
        raise OSError("response interrupted")
    jobs = SyncJobs(ledger)
    with pytest.raises(OSError):
        jobs.run("openai", "image", {}, tmp_path / "i.png", 1, fail)
    with pytest.raises(UncertainSubmission):
        jobs.run("openai", "image", {}, tmp_path / "i.png", 1, fail)
    assert len(calls) == 1
    ledger.close()


def test_budget_and_inputs_cannot_change_on_resume(tmp_path):
    path = tmp_path / "state.db"
    ledger = Ledger(path, 10, True)
    ledger.bind("plan", "first")
    with pytest.raises(CinemaError):
        ledger.bind("plan", "second")
    ledger.close()
    with pytest.raises(BudgetError):
        Ledger(path, 20, True)


def test_os_lock_prevents_two_runs(tmp_path):
    with run_lock(tmp_path):
        with pytest.raises(CinemaError):
            with run_lock(tmp_path):
                pass
