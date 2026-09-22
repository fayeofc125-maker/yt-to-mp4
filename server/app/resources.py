"""Admission controls for local media resources."""

from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path


class ResourceAdmissionError(RuntimeError):
    """Raised when a job cannot be admitted without exhausting resources."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ResourceReservation:
    bytes_reserved: int
    heavy: bool


class ResourceGuard:
    """Constant-time reservations plus a filesystem free-space check."""

    def __init__(
        self,
        *,
        temp_budget_bytes: int | None = None,
        min_free_bytes: int | None = None,
        max_heavy_jobs: int | None = None,
        max_memory_mb: int | None = None,
    ):
        self.temp_budget_bytes = (
            _env_int("TEMP_STORAGE_BUDGET_BYTES", 20 * 1024**3)
            if temp_budget_bytes is None
            else temp_budget_bytes
        )
        self.min_free_bytes = (
            _env_int("TEMP_STORAGE_MIN_FREE_BYTES", 1 * 1024**3)
            if min_free_bytes is None
            else min_free_bytes
        )
        self.max_heavy_jobs = (
            _env_int("RESOURCE_MAX_HEAVY_JOBS", 0) if max_heavy_jobs is None else max_heavy_jobs
        )
        self.max_memory_mb = (
            _env_int("RESOURCE_MAX_MEMORY_MB", 0) if max_memory_mb is None else max_memory_mb
        )
        self._reserved_bytes = 0
        self._heavy_jobs = 0
        self._reserved_memory_mb = 0
        self._reservations: dict[str, tuple[ResourceReservation, int]] = {}
        self._lock = threading.Lock()
        if self.temp_budget_bytes < 0 or self.min_free_bytes < 0:
            raise ValueError(
                "TEMP_STORAGE_BUDGET_BYTES and TEMP_STORAGE_MIN_FREE_BYTES cannot be negative"
            )
        if self.max_heavy_jobs < 0 or self.max_memory_mb < 0:
            raise ValueError(
                "RESOURCE_MAX_HEAVY_JOBS and RESOURCE_MAX_MEMORY_MB cannot be negative"
            )

    @property
    def reserved_bytes(self) -> int:
        with self._lock:
            return self._reserved_bytes

    def reserve(
        self,
        job_id: str,
        root: Path,
        *,
        estimated_bytes: int,
        heavy: bool,
        memory_mb: int,
    ) -> ResourceReservation:
        if estimated_bytes < 0 or memory_mb < 0:
            raise ValueError("resource estimates cannot be negative")
        usage = shutil.disk_usage(root)
        with self._lock:
            if job_id in self._reservations:
                raise ResourceAdmissionError("duplicate resource reservation")
            if usage.free - self._reserved_bytes < self.min_free_bytes + estimated_bytes:
                raise ResourceAdmissionError("insufficient disk space")
            if self._reserved_bytes + estimated_bytes > self.temp_budget_bytes:
                raise ResourceAdmissionError("temporary storage budget exceeded")
            if heavy and self.max_heavy_jobs and self._heavy_jobs >= self.max_heavy_jobs:
                raise ResourceAdmissionError("heavy job capacity reached")
            if self.max_memory_mb and self._reserved_memory_mb + memory_mb > self.max_memory_mb:
                raise ResourceAdmissionError("memory admission capacity reached")
            reservation = ResourceReservation(estimated_bytes, heavy)
            self._reservations[job_id] = (reservation, memory_mb)
            self._reserved_bytes += estimated_bytes
            self._heavy_jobs += int(heavy)
            self._reserved_memory_mb += memory_mb
            return reservation

    def release(self, job_id: str) -> None:
        with self._lock:
            item = self._reservations.pop(job_id, None)
            if item is None:
                return
            reservation, memory_mb = item
            self._reserved_bytes -= reservation.bytes_reserved
            self._heavy_jobs -= int(reservation.heavy)
            self._reserved_memory_mb -= memory_mb


def _env_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value
