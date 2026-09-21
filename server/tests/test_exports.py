import time
import zipfile

from fastapi.testclient import TestClient

from app import main
from app.jobs import ExportJobManager
from app.media import Clip


def test_export_validates_ranges_and_returns_safe_zip(tmp_path, monkeypatch):
    def runner(spec, out_dir):
        out_dir.mkdir(exist_ok=True)
        path = out_dir / "clip.mp4"
        path.write_bytes(f"{spec.start}".encode())
        return Clip(path, "A: title/with * unsafe?")

    monkeypatch.setattr(
        main,
        "export_jobs",
        ExportJobManager(runner, workers=1, root=tmp_path / "exports"),
    )
    client = TestClient(main.app)
    response = client.post(
        "/api/exports",
        json={
            "url": "https://www.youtube.com/watch?v=x",
            "res": 1080,
            "ranges": [{"start": 1, "end": 2}, {"start": 4, "end": 5}],
        },
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        status = client.get(f"/api/exports/{job_id}").json()
        if status["status"] == "done":
            break
        time.sleep(0.01)
    assert status["filename"] == "A titlewith unsafe.zip"
    download = client.get(f"/api/exports/{job_id}/file")
    archive_path = tmp_path / "result.zip"
    archive_path.write_bytes(download.content)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == [
            "A titlewith unsafe 01 (1s-2s).mp4",
            "A titlewith unsafe 02 (4s-5s).mp4",
        ]


def test_export_rejects_overlapping_ranges():
    client = TestClient(main.app)
    response = client.post(
        "/api/exports",
        json={
            "url": "https://www.youtube.com/watch?v=x",
            "res": 1080,
            "ranges": [{"start": 1, "end": 3}, {"start": 2, "end": 4}],
        },
    )
    assert response.status_code == 202
