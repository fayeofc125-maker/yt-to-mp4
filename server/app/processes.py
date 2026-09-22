"""Process groups used by media jobs."""

import os
import signal
import subprocess
import threading
import time
from collections.abc import Iterable
from contextlib import suppress
from contextvars import ContextVar

from yt_dlp.utils import Popen as YtDlpPopen

_active_group: ContextVar["ProcessGroup | None"] = ContextVar(
    "active_media_process_group", default=None
)
_original_yt_dlp_init = YtDlpPopen.__init__


def _track_yt_dlp_process(self, *args, **kwargs):
    _original_yt_dlp_init(self, *args, **kwargs)
    group = _active_group.get()
    if group is not None:
        group.add(self)


YtDlpPopen.__init__ = _track_yt_dlp_process


class ProcessCancelledError(RuntimeError):
    """Raised when a media process is cancelled."""


def terminate_process_tree(process: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    """Stop a process and its descendants, tolerating processes that already exited."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=0.25)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        with suppress(OSError):
            process.kill()


class ProcessGroup:
    """Track and terminate all subprocesses owned by one media operation."""

    def __init__(self) -> None:
        self._processes: set[subprocess.Popen] = set()
        self._lock = threading.Lock()

    def add(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.add(process)

    def remove(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(process)

    def terminate_all(self) -> None:
        with self._lock:
            processes = tuple(self._processes)
        for process in processes:
            terminate_process_tree(process)

    def run(
        self,
        args: list[str],
        timeout: float,
        cancelled: threading.Event | None = None,
    ) -> None:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "shell": False}
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            kwargs["creationflags"] = creationflags
        process = subprocess.Popen(args, **kwargs)
        self.add(process)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if cancelled is not None and cancelled.is_set():
                    terminate_process_tree(process)
                    raise ProcessCancelledError
                if time.monotonic() >= deadline:
                    terminate_process_tree(process)
                    raise subprocess.TimeoutExpired(args, timeout)
                time.sleep(0.02)
            stdout, stderr = process.communicate()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, args, stdout, stderr)
        finally:
            self.remove(process)

    def __enter__(self) -> "ProcessGroup":
        self._token = _active_group.set(self)
        return self

    def __exit__(self, *_exc: object) -> None:
        _active_group.reset(self._token)
        self.terminate_all()


def terminate_processes(groups: Iterable[ProcessGroup]) -> None:
    """Terminate multiple operation groups during job cancellation."""
    for group in groups:
        group.terminate_all()
