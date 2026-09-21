import threading
import time

import pytest

from app.formats import Quality
from app.jobs import JobManager, JobStatus, QueueFull, TooManyJobs
from app.media import Clip, ClipSpec, Mode

SPEC = ClipSpec("https://youtu.be/x", 10, 40, Quality(1080), Mode.EXACT)


def wait_for(job, status, timeout=3):
    deadline = time.time() + timeout
    while job.status is not status:
        assert time.time() < deadline, f"job stuck in {job.status}"
        time.sleep(0.01)


@pytest.fixture
def gate():
    return threading.Event()


@pytest.fixture
def manager(tmp_path, gate):
    def runner(spec, out_dir):
        gate.wait(3)  # lets a test hold a job in the "working" state
        path = out_dir / "clip.mp4"
        path.write_bytes(b"data")
        return Clip(path, "Title")

    return JobManager(runner, workers=1, ttl=60, root=tmp_path / "jobs")


def test_job_runs_to_completion(manager, gate):
    job = manager.submit(SPEC, "a")
    wait_for(job, JobStatus.WORKING)
    gate.set()
    wait_for(job, JobStatus.DONE)
    assert job.clip.path.read_bytes() == b"data"
    assert job.filename == "Title (10s-40s).mp4"
    assert 0 < manager.expires_in(job) <= 60


def test_waiting_jobs_report_their_place_in_line(manager, gate):
    first = manager.submit(SPEC, "a")
    wait_for(first, JobStatus.WORKING)
    second = manager.submit(SPEC, "b")
    third = manager.submit(SPEC, "c")
    assert [manager.position(j) for j in (first, second, third)] == [None, 1, 2]
    gate.set()


def test_one_user_cannot_flood_the_queue(manager):
    manager.submit(SPEC, "a")
    manager.submit(SPEC, "a")
    with pytest.raises(TooManyJobs):
        manager.submit(SPEC, "a")
    manager.submit(SPEC, "b")  # someone else is unaffected


def test_queue_has_a_ceiling(manager, monkeypatch):
    monkeypatch.setattr("app.jobs.MAX_QUEUED", 2)
    for client in "abc":  # one running + two queued
        manager.submit(SPEC, client)
    with pytest.raises(QueueFull):
        manager.submit(SPEC, "d")


def test_failed_job_reports_error_and_cleans_up(tmp_path):
    def runner(spec, out_dir):
        raise RuntimeError("boom")

    manager = JobManager(runner, root=tmp_path / "jobs")
    job = manager.submit(SPEC, "a")
    wait_for(job, JobStatus.FAILED)
    assert job.error == "Something went wrong on our side."
    assert not job.work_dir.exists()


def test_timeout_failure_is_clean_and_does_not_retry(tmp_path):
    manager = JobManager(
        lambda spec, out_dir: (_ for _ in ()).throw(TimeoutError("test timeout")),
        max_attempts=3,
        root=tmp_path / "jobs",
    )
    job = manager.submit(SPEC, "a")
    wait_for(job, JobStatus.FAILED)
    assert "timed out" in job.error
    assert not job.work_dir.exists()


def test_active_download_reference_blocks_ttl_cleanup(tmp_path):
    manager = JobManager(
        lambda spec, out_dir: _clip(out_dir),
        ttl=0,
        cleanup_grace=0,
        root=tmp_path / "jobs",
    )
    job = manager.submit(SPEC, "a")
    wait_for(job, JobStatus.DONE)
    assert manager.acquire_download(job.id, allow_expired=True) is job
    time.sleep(0.01)
    assert manager.get(job.id) is job
    assert job.work_dir.exists()
    manager.release_download(job.id)
    time.sleep(0.01)
    assert manager.get(job.id) is None
    assert not job.work_dir.exists()


def test_finished_jobs_and_files_expire(tmp_path, gate):
    gate.set()
    manager = JobManager(lambda spec, out_dir: _clip(out_dir), ttl=0, root=tmp_path / "jobs")
    job = manager.submit(SPEC, "a")
    wait_for(job, JobStatus.DONE)
    time.sleep(0.01)
    assert manager.get(job.id) is None
    assert not job.work_dir.exists()


def test_estimate_is_learned_from_finished_jobs(manager, gate):
    assert manager.estimate(SPEC) is None
    gate.set()
    job = manager.submit(SPEC, "a")
    wait_for(job, JobStatus.DONE)
    assert manager.estimate(SPEC) > 0
    assert manager.estimate(SPEC._replace(mode=Mode.FAST)) is None  # tracked per mode


def _clip(out_dir):
    path = out_dir / "clip.mp4"
    path.write_bytes(b"x")
    return Clip(path, "T")
