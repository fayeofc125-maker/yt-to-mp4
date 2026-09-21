"""SQLModel persistence records (API-facing job objects remain in jobs.py)."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class JobRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    kind: str = Field(index=True)
    spec_json: str
    client: str = Field(index=True)
    work_dir: str
    status: str = Field(index=True)
    progress_phase: str = "queued"
    progress_percent: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    result_url: str | None = None
    object_key: str | None = None
    result_size: int | None = None
    spec_metadata: str = "{}"
    cancellation_requested: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    phase: str = "queued"
    percent: int = 0
    title: str = "export"
    path: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    next_run_at: datetime | None = None
