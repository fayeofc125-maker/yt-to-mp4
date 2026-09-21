import sys
import time
import types

import pytest

from app import media
from app.jobs import JobStatus, TranscriptJobManager


def test_whisper_is_disabled_without_flag_or_optional_package(monkeypatch):
    monkeypatch.delenv("ENABLE_WHISPER_FALLBACK", raising=False)
    monkeypatch.setattr(media.importlib.util, "find_spec", lambda name: None)
    assert media.whisper_is_configured() is False


def test_whisper_memory_guard_fails_cleanly(monkeypatch):
    monkeypatch.setenv("WHISPER_MIN_AVAILABLE_MEMORY_MB", "512")
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        types.SimpleNamespace(virtual_memory=lambda: types.SimpleNamespace(available=1)),
    )
    with pytest.raises(media.WhisperResourceError, match="available memory"):
        media._check_whisper_memory()


def test_whisper_model_configuration_and_progress(monkeypatch, tmp_path):
    class Word:
        start, end, word = 0.1, 0.2, " hello"

    class Segment:
        start, end, text, words = 0.0, 5.0, " hello", [Word()]

    class Model:
        def __init__(self, model, **options):
            assert model == "small"
            assert options["device"] == "cpu"
            assert options["compute_type"] == "int8"

        def transcribe(self, audio, word_timestamps):
            return iter([Segment()]), object()

    fake_module = types.SimpleNamespace(WhisperModel=Model)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.setattr(media.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setenv("ENABLE_WHISPER_FALLBACK", "true")
    monkeypatch.setenv("WHISPER_MODEL", "small")
    monkeypatch.setattr(media, "fetch_info", lambda url: {"duration": 10})
    monkeypatch.setattr(media, "_check_whisper_memory", lambda: None)

    class FakeYDL:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def extract_info(self, url, download):
            (tmp_path / "audio.m4a").write_bytes(b"audio")
            return {"filepath": str(tmp_path / "audio.m4a")}

        def prepare_filename(self, info):
            return info["filepath"]

    monkeypatch.setattr(media, "YoutubeDL", lambda options: FakeYDL())
    progress = []
    result = media.fetch_whisper_transcript(
        "https://www.youtube.com/watch?v=x",
        progress=lambda phase, percent: progress.append((phase, percent)),
    )
    assert result[0]["words"][0]["text"] == "hello"
    assert progress[0] == ("downloading", 5)
    assert progress[-1] == ("complete", 100)


def test_transcript_manager_reports_progress_and_resource_failure():
    def runner(url, progress=None):
        progress("loading_model", 10)
        progress("transcribing", 60)
        return [{"start": 0, "end": 1, "text": "ok"}]

    manager = TranscriptJobManager(runner, workers=1, max_concurrent=1)
    job = manager.submit("https://www.youtube.com/watch?v=x", "client")
    for _ in range(100):
        current = manager.get(job.id)
        if current.status is JobStatus.DONE:
            break
        time.sleep(0.005)
    assert current.status is JobStatus.DONE
    assert current.percent == 100
    assert current.phase == "complete"

    failing = TranscriptJobManager(
        lambda url: (_ for _ in ()).throw(RuntimeError("memory pressure")),
        workers=1,
        max_concurrent=1,
    )
    failed = failing.submit("https://www.youtube.com/watch?v=x", "client")
    for _ in range(100):
        current = failing.get(failed.id)
        if current.status is JobStatus.FAILED:
            break
        time.sleep(0.005)
    assert current.error == "memory pressure"
