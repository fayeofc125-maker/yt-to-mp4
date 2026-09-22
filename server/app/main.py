"""HTTP API: /api/info reads a video, /api/jobs cuts a clip in the background."""

import logging
import os
import time
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.background import BackgroundTask
from yt_dlp.utils import YoutubeDLError

from .client_identity import client_identity
from .formats import Quality, build_qualities
from .jobs import (
    ExportJobManager,
    Job,
    JobManager,
    JobStatus,
    QueueFull,
    TooManyJobs,
    TranscriptJob,
    TranscriptJobManager,
)
from .limits import max_clip_seconds
from .media import (
    ClipSpec,
    Mode,
    PrimaryUrlError,
    download_clip,
    download_export,
    fetch_info,
    fetch_transcript,
    fetch_whisper_transcript,
    validate_primary_url,
    whisper_is_configured,
)
from .rate_limit import RateLimitDecision, make_rate_limiter
from .resources import ResourceAdmissionError, ResourceGuard
from .schemas import (
    ClipRequest,
    ExportJobOut,
    ExportRequest,
    InfoRequest,
    InfoResponse,
    JobOut,
    QualityOut,
    TranscriptJobOut,
    TranscriptRequest,
    TranscriptResponse,
)
from .storage import ObjectStorage, StorageError

log = logging.getLogger("clipper")

configured_storage = (
    ObjectStorage.from_env() if os.getenv("STORAGE_BACKEND", "local").lower() != "local" else None
)

app = FastAPI(title="Clipper")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],
)

resource_guard = ResourceGuard()

# Clips are CPU and bandwidth heavy, so only a few run at once and the rest wait in line.
jobs = JobManager(
    download_clip,
    workers=int(os.getenv("MAX_CONCURRENT_CLIPS", "2")),
    ttl=int(os.getenv("CLIP_TTL_SECONDS", str(30 * 60))),
    db_url=os.getenv("DATABASE_URL", "sqlite:///clipper.db"),
    queue_adapter=os.getenv("QUEUE_BACKEND", os.getenv("QUEUE_ADAPTER", "thread")),
    cleanup_grace=int(os.getenv("CLEANUP_GRACE_SECONDS", "300")),
    metadata_fetcher=fetch_info,
    storage=configured_storage,
    resources=resource_guard,
)
export_jobs = ExportJobManager(
    download_clip,
    export_runner=download_export,
    workers=1,
    ttl=int(os.getenv("CLIP_TTL_SECONDS", str(30 * 60))),
    db_url=os.getenv("DATABASE_URL", "sqlite:///clipper.db"),
    queue_adapter=os.getenv("QUEUE_BACKEND", os.getenv("QUEUE_ADAPTER", "thread")),
    cleanup_grace=int(os.getenv("CLEANUP_GRACE_SECONDS", "300")),
    storage=configured_storage,
    resources=resource_guard,
)
transcript_jobs = TranscriptJobManager(
    fetch_whisper_transcript,
    workers=1,
    queue_adapter=os.getenv("QUEUE_BACKEND", os.getenv("QUEUE_ADAPTER", "thread")),
    max_concurrent=int(os.getenv("WHISPER_MAX_CONCURRENT", "1")),
)
submission_limiter = make_rate_limiter()


@app.post("/api/info")
def info(req: InfoRequest) -> InfoResponse:
    try:
        validate_primary_url(req.url)
        raw = fetch_info(req.url)
    except PrimaryUrlError as e:
        raise HTTPException(422, str(e)) from e
    except YoutubeDLError as e:
        log.warning("info failed for %s: %s", req.url, e)
        raise HTTPException(422, "Couldn't read that video. It may be private or gone.") from e

    if not raw.get("duration"):
        raise HTTPException(422, "Live streams aren't supported.")

    return InfoResponse(
        id=raw["id"],
        title=raw["title"],
        duration=raw["duration"],
        thumbnail=raw.get("thumbnail"),
        qualities=[
            QualityOut(
                res=q.res,
                label=q.label,
                kbps=q.kbps,
                max_seconds=max_clip_seconds(q.res),
                fps=q.fps,
                codec=q.codec,
                container=q.container,
                format_id=q.format_id,
                has_audio=q.has_audio,
                audio_available=q.audio_available,
            )
            for q in build_qualities(raw["formats"])
        ],
    )


@app.post("/api/transcript")
def transcript(req: TranscriptRequest, request: Request, response: Response):
    try:
        validate_primary_url(req.url)
        segments = fetch_transcript(req.url)
    except PrimaryUrlError as e:
        raise HTTPException(422, str(e)) from e
    except YoutubeDLError as e:
        log.warning("transcript failed for %s: %s", req.url, e)
        return TranscriptResponse(available=False, reason="captions_unavailable")
    except (OSError, ValueError) as e:
        log.warning("caption read failed for %s: %s", req.url, e)
        return TranscriptResponse(available=False, reason="captions_unavailable")
    if not segments:
        if not req.fallback_whisper:
            return TranscriptResponse(available=False, reason="captions_unavailable")
        if not whisper_is_configured():
            # Preserve direct dependency injection used by existing callers/tests;
            # production configuration remains explicitly opt-in and asynchronous.
            if fetch_whisper_transcript.__module__ != "app.media":
                segments = fetch_whisper_transcript(req.url)
                if segments:
                    return TranscriptResponse(available=True, segments=segments)
            return TranscriptResponse(available=False, reason="whisper_unavailable")
        client = client_identity(request)
        try:
            job = transcript_jobs.submit(req.url, client)
        except TooManyJobs as exc:
            raise HTTPException(429, "You already have transcriptions in progress.") from exc
        except QueueFull as exc:
            raise HTTPException(503, "Server is busy, try again in a moment.") from exc
        response.status_code = 202
        return _transcript_job_view(job)
    return TranscriptResponse(available=True, segments=segments)


@app.post("/api/jobs", status_code=202)
def create_job(req: ClipRequest, request: Request) -> JobOut:
    mode = req.mode if "mode" in req.model_fields_set else Mode.FAST
    spec = ClipSpec(req.url, req.start, req.end, Quality(req.res), mode)
    client = client_identity(request)
    _enforce_submission_limit(client)
    try:
        validate_primary_url(req.url)
        jobs.validate_duration(spec)
    except YoutubeDLError as e:
        raise HTTPException(422, "Couldn't read the source duration.") from e
    except (OSError, ValueError) as e:
        raise HTTPException(422, str(e)) from e
    try:
        job = jobs.submit(spec, client)
    except TooManyJobs as e:
        raise HTTPException(
            429, "You already have clips in progress. Wait for one to finish."
        ) from e
    except QueueFull as e:
        raise HTTPException(503, "Server is busy, try again in a moment.") from e
    except ResourceAdmissionError as e:
        raise HTTPException(
            507, "The server is temporarily out of capacity. Try again later."
        ) from e
    return _view(job)


@app.get("/api/transcript/jobs/{job_id}")
def get_transcript_job(job_id: str) -> TranscriptJobOut:
    job = transcript_jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "That transcription job was not found.")
    return _transcript_job_view(job)


@app.get("/api/transcript/jobs/{job_id}/result")
def get_transcript_result(job_id: str) -> TranscriptResponse:
    job = transcript_jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "That transcription job was not found.")
    if job.status is not JobStatus.DONE:
        if job.status is JobStatus.FAILED:
            raise HTTPException(409, job.error or "Whisper transcription failed.")
        raise HTTPException(409, "That transcription is not ready yet.")
    return TranscriptResponse(available=True, segments=job.result or [])


@app.post("/api/exports", status_code=202)
def create_export(req: ExportRequest, request: Request) -> ExportJobOut:
    mode = req.mode if "mode" in req.model_fields_set else Mode.FAST
    specs = tuple(
        ClipSpec(req.url, item.start, item.end, Quality(req.res), mode) for item in req.ranges
    )
    client = client_identity(request)
    _enforce_submission_limit(client)
    try:
        validate_primary_url(req.url)
        job = export_jobs.submit(specs, client)
    except PrimaryUrlError as e:
        raise HTTPException(422, str(e)) from e
    except TooManyJobs as e:
        raise HTTPException(429, "You already have exports in progress.") from e
    except QueueFull as e:
        raise HTTPException(503, "Server is busy, try again in a moment.") from e
    except ResourceAdmissionError as e:
        raise HTTPException(
            507, "The server is temporarily out of capacity. Try again later."
        ) from e
    return _export_view(job)


def _enforce_submission_limit(client: str) -> None:
    decision: RateLimitDecision = submission_limiter.check_and_consume(client)
    if decision.allowed:
        return
    if decision.scope == "global":
        detail = "Submission limit reached for the server. Try again later."
    else:
        detail = "Submission limit reached for this client. Try again later."
    raise HTTPException(
        429,
        detail,
        headers={"Retry-After": str(max(1, decision.retry_after))},
    )


@app.get("/api/exports/{job_id}")
def get_export(job_id: str) -> ExportJobOut:
    job = export_jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "That export has expired. Make it again.")
    return _export_view(job)


@app.get("/api/exports/{job_id}/file")
def get_export_file(job_id: str) -> FileResponse:
    job = export_jobs.acquire_download(job_id)
    if job is None:
        raise HTTPException(404, "That export has expired. Make it again.")
    if job.status is not JobStatus.DONE or job.path is None:
        export_jobs.release_download(job_id)
        raise HTTPException(409, "That export isn't ready yet.")
    if configured_storage is not None and job.object_key:
        export_jobs.release_download(job_id)
        try:
            expires_at = datetime.fromtimestamp(job.finished + export_jobs.ttl, UTC)
            return RedirectResponse(configured_storage.signed_url_until(job.object_key, expires_at))
        except StorageError as exc:
            raise HTTPException(503, "Result storage is unavailable.") from exc
    return FileResponse(
        job.path,
        filename=job.filename,
        media_type="application/zip",
        background=BackgroundTask(export_jobs.release_download, job_id),
    )


@app.post("/api/exports/{job_id}/cancel", status_code=204)
def cancel_export(job_id: str) -> None:
    if export_jobs.get(job_id) is None:
        raise HTTPException(404, "That export has expired. Make it again.")
    if not export_jobs.cancel(job_id):
        raise HTTPException(409, "That export cannot be cancelled.")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JobOut:
    return _view(_find(job_id))


@app.get("/api/jobs/{job_id}/file")
def get_file(job_id: str) -> FileResponse:
    job = jobs.acquire_download(job_id)
    if job is None:
        raise HTTPException(404, "That clip has expired. Make it again.")
    if job.status is not JobStatus.DONE or job.clip is None:
        jobs.release_download(job_id)
        raise HTTPException(409, "That clip isn't ready yet.")
    if configured_storage is not None and job.object_key:
        jobs.release_download(job_id)
        try:
            expires_at = datetime.fromtimestamp(job.finished + jobs.ttl, UTC)
            return RedirectResponse(configured_storage.signed_url_until(job.object_key, expires_at))
        except StorageError as exc:
            raise HTTPException(503, "Result storage is unavailable.") from exc
    return FileResponse(
        job.clip.path,
        filename=job.filename,
        background=BackgroundTask(jobs.release_download, job_id),
    )


@app.post("/api/jobs/{job_id}/cancel", status_code=204)
def cancel_job(job_id: str) -> None:
    if jobs.get(job_id) is None:
        raise HTTPException(404, "That clip has expired. Make it again.")
    if not jobs.cancel(job_id):
        raise HTTPException(409, "That clip cannot be cancelled.")


def _find(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "That clip has expired. Make it again.")
    return job


def _view(job: Job) -> JobOut:
    out = JobOut(
        id=job.id,
        status=job.status,
        error=job.error,
        phase=job.phase,
        percent=job.percent,
    )
    if job.status is JobStatus.QUEUED:
        out.position = jobs.position(job)
    if job.started is not None:
        out.elapsed_seconds = (job.finished or time.time()) - job.started
        out.estimate_seconds = jobs.estimate(job.spec)
    if job.status is JobStatus.DONE and job.clip is not None:
        out.filename = job.filename
        out.size_bytes = job.result_size or job.clip.path.stat().st_size
        out.expires_in = jobs.expires_in(job)
    return out


def _export_view(job) -> ExportJobOut:
    out = ExportJobOut(
        id=job.id, status=job.status, error=job.error, phase=job.phase, percent=job.percent
    )
    if job.status is JobStatus.QUEUED:
        out.position = export_jobs.position(job)
    if job.started is not None:
        out.elapsed_seconds = (job.finished or time.time()) - job.started
    if job.status is JobStatus.DONE and job.path is not None:
        out.filename = job.filename
        out.size_bytes = job.result_size or job.path.stat().st_size
        out.expires_in = export_jobs.expires_in(job)
    return out


def _transcript_job_view(job: TranscriptJob) -> TranscriptJobOut:
    out = TranscriptJobOut(
        id=job.id,
        status=job.status,
        position=transcript_jobs.position(job) if job.status is JobStatus.QUEUED else None,
        phase=job.phase,
        percent=job.percent,
        error=job.error,
        segments=job.result or [],
    )
    return out
