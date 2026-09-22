import os
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.formats import Quality
from app.jobs import ExportJobManager, JobManager, JobStatus
from app.media import Clip, ClipSpec, Mode
from app.storage import ObjectStorage, StorageError, StoredObject

SPEC = ClipSpec("https://youtu.be/x", 1, 3, Quality(720), Mode.FAST)


class FakeS3:
    def __init__(self):
        self.uploads = []
        self.deleted = []

    def upload_file(self, source, bucket, key):
        self.uploads.append((source, bucket, key))

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.last_expires = ExpiresIn
        return f"https://storage.test/{Params['Key']}?X-Amz-Expires={ExpiresIn}"


def wait(job):
    deadline = time.time() + 2
    while job.status in {JobStatus.QUEUED, JobStatus.WORKING}:
        assert time.time() < deadline
        time.sleep(0.01)


def test_s3_adapter_upload_key_and_signed_expiry(tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"result")
    client = FakeS3()
    storage = ObjectStorage("s3", bucket="clipper-results", client=client, signed_url_seconds=300)
    stored = storage.upload(source, "clips/job-1/clip.mp4")
    assert stored == StoredObject("clips/job-1/clip.mp4", 6)
    assert client.uploads[0][2] == "clips/job-1/clip.mp4"
    assert "X-Amz-Expires=120" in storage.signed_url(stored.key, 120)
    storage.delete(stored.key)
    assert client.deleted == [{"Bucket": "clipper-results", "Key": stored.key}]


def test_signed_url_never_exceeds_remaining_job_ttl():
    client = FakeS3()
    storage = ObjectStorage("s3", client=client, signed_url_seconds=7200)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    storage.signed_url_until("clips/job/clip.mp4", now + timedelta(minutes=90), now)
    assert client.last_expires == 3600


def test_signed_url_uses_short_remaining_ttl_and_rejects_near_expiry():
    client = FakeS3()
    storage = ObjectStorage("s3", client=client, signed_url_seconds=7200)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    storage.signed_url_until("clips/job/clip.mp4", now + timedelta(seconds=17), now)
    assert client.last_expires == 17
    try:
        storage.signed_url_until("clips/job/clip.mp4", now, now)
    except RuntimeError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("expired result was signed")


def test_manager_uploads_completed_clip_with_convention(tmp_path):
    storage = ObjectStorage("local", root=tmp_path / "objects")

    def runner(spec, out_dir):
        path = out_dir / "clip.mp4"
        path.write_bytes(b"clip")
        return Clip(path, "Title")

    manager = JobManager(runner, root=tmp_path / "jobs", storage=storage)
    job = manager.submit(SPEC, "client")
    wait(job)
    assert job.status is JobStatus.DONE
    assert job.object_key == f"clips/{job.id}/Title (1s-3s).mp4"
    assert (storage.root / job.object_key).read_bytes() == b"clip"


def test_cleanup_race_preserves_object_until_active_download_releases(tmp_path, monkeypatch):
    storage = ObjectStorage("local", root=tmp_path / "objects")

    def runner(spec, out_dir):
        path = out_dir / "clip.mp4"
        path.write_bytes(b"clip")
        return Clip(path, "Title")

    manager = JobManager(
        runner,
        ttl=10,
        cleanup_grace=5,
        root=tmp_path / "jobs",
        storage=storage,
    )
    job = manager.submit(SPEC, "client")
    wait(job)
    assert job.status is JobStatus.DONE
    object_path = storage.root / job.object_key
    assert object_path.exists()

    clock = [job.finished]
    monkeypatch.setattr("app.jobs.time.time", lambda: clock[0])
    assert manager.acquire_download(job.id, allow_expired=True) is job
    clock[0] = job.finished + manager.ttl + manager.cleanup_grace + 0.01
    manager._expire()
    assert manager.get(job.id) is job
    assert object_path.exists()

    manager.release_download(job.id)
    manager._expire()
    assert manager.get(job.id) is None
    assert not object_path.exists()


def test_export_manager_uploads_zip_with_convention(tmp_path):
    storage = ObjectStorage("local", root=tmp_path / "objects")

    def runner(spec, out_dir):
        path = out_dir / "clip.mp4"
        path.write_bytes(b"clip")
        return Clip(path, "Title")

    manager = ExportJobManager(runner, root=tmp_path / "jobs", storage=storage)
    job = manager.submit((SPEC,), "client")
    wait(job)
    assert job.status is JobStatus.DONE
    assert job.object_key == f"exports/{job.id}/Title.zip"
    assert (storage.root / job.object_key).is_file()


def test_local_reconciliation_preserves_active_and_valid_objects(tmp_path):
    storage = ObjectStorage("local", root=tmp_path / "objects")
    active = storage.root / "clips" / "active-job" / "clip.mp4"
    valid = storage.root / "exports" / "valid-job" / "export.zip"
    orphan = storage.root / "clips" / "old-job" / "partial.mp4"
    recent = storage.root / "clips" / "recent-job" / "partial.mp4"
    for path in (active, valid, orphan, recent):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    old = time.time() - 100
    os.utime(orphan, (old, old))
    assert storage.reconcile(
        {"clips/active-job/clip.mp4", "exports/valid-job/export.zip"},
        orphan_age_seconds=60,
    ) == ["clips/old-job/partial.mp4"]
    assert active.exists()
    assert valid.exists()
    assert not orphan.exists()
    assert recent.exists()


def test_local_reconciliation_is_safe_for_unrelated_paths_and_traversal(tmp_path):
    storage = ObjectStorage("local", root=tmp_path / "objects")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    unrelated = storage.root / "unrelated" / "old.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"keep")
    old = time.time() - 100
    os.utime(unrelated, (old, old))
    assert storage.reconcile(set(), orphan_age_seconds=60) == []
    assert unrelated.exists()
    with pytest.raises(StorageError):
        storage.delete("../outside.txt")
    with pytest.raises(StorageError):
        storage.delete("clips/job/../../outside.txt")
    assert outside.exists()


def test_local_reconciliation_tolerates_missing_and_failed_deletions(tmp_path, monkeypatch):
    storage = ObjectStorage("local", root=tmp_path / "objects")
    failing = storage.root / "clips" / "failed-job" / "a.mp4"
    removable = storage.root / "clips" / "remove-job" / "b.mp4"
    for path in (failing, removable):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        old = time.time() - 100
        os.utime(path, (old, old))
    original_unlink = type(failing).unlink

    def unlink(path, *args, **kwargs):
        if path == failing:
            raise OSError("locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(type(failing), "unlink", unlink)
    assert storage.reconcile(set(), orphan_age_seconds=60) == ["clips/remove-job/b.mp4"]
    removable.unlink(missing_ok=True)
    assert storage.reconcile(set(), orphan_age_seconds=60) == []
    assert failing.exists()


def test_reconciliation_removes_old_failed_work_dirs_but_not_recent_or_active(tmp_path):
    root = tmp_path / "jobs"
    active = root / "active-job"
    failed = root / "failed-job"
    recent = root / "recent-job"
    for path in (active, failed, recent):
        path.mkdir(parents=True)
        (path / "partial.mp4").write_bytes(b"x")
    old = time.time() - 100
    os.utime(failed, (old, old))

    def runner(spec, out_dir):
        path = out_dir / "clip.mp4"
        path.write_bytes(b"x")
        return Clip(path, "Title")

    manager = JobManager(
        runner,
        root=root,
        db_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        reconciliation_age=60,
    )
    manager.reconcile()
    assert active.exists()
    assert recent.exists()
    assert not failed.exists()
