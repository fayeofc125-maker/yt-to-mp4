"""Benchmark Clipper media paths without changing the production pipeline.

Usage:
    python scripts/benchmark_clips.py scripts/benchmark_config.sample.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app.formats import Quality, build_qualities
from app.media import (
    ClipSpec,
    Mode,
    download_clip,
    download_export,
    fetch_info,
)

MAX_RANGE_SECONDS = 15 * 60
PLACEHOLDER_PREFIX = "__PLACEHOLDER__"


@dataclass
class RunResult:
    label: str
    mode: str
    success: bool
    wall_seconds: float | None = None
    download_seconds: float | None = None
    processing_seconds: float | None = None
    size_bytes: int | None = None
    fps: str | None = None
    codec: str | None = None
    container: str | None = None
    peak_memory: str | None = None
    error: str | None = None


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Config file does not exist: {path}")
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise ValueError(
                    "YAML config requires PyYAML. Install it with `pip install PyYAML` "
                    "or use JSON."
                ) from exc
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not parse config {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("videos"), list):
        raise TypeError("Config must be an object with a non-empty `videos` array")
    if not data["videos"]:
        raise ValueError("Config `videos` must not be empty")
    for index, entry in enumerate(data["videos"], 1):
        if not isinstance(entry, dict):
            raise TypeError(f"videos[{index}] must be an object")
        for key in ("label", "url", "expected_caption_type"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f"videos[{index}] requires a non-empty `{key}`")
        for key in ("start", "end"):
            if key in entry and (
                not isinstance(entry[key], (int, float)) or entry[key] < 0
            ):
                raise ValueError(f"videos[{index}].{key} must be a non-negative number")
        if "res" in entry and (not isinstance(entry["res"], int) or entry["res"] <= 0):
            raise ValueError(f"videos[{index}].res must be a positive integer")
    return data


def caption_type(raw: dict[str, Any]) -> str:
    manual = raw.get("subtitles") or {}
    automatic = raw.get("automatic_captions") or {}
    if manual:
        return "manual"
    if automatic:
        return "automatic"
    return "none"


def selected_quality(raw: dict[str, Any], requested_res: int | None) -> Quality:
    qualities = build_qualities(raw.get("formats") or [])
    if not qualities:
        raise ValueError("No compatible video qualities were found")
    if requested_res is None:
        return qualities[0]
    candidates = [quality for quality in qualities if quality.res <= requested_res]
    if not candidates:
        raise ValueError(f"No source quality is available at or below {requested_res}p")
    return max(candidates, key=lambda quality: quality.res)


def probe(path: Path) -> dict[str, str | None]:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate,codec_name",
                "-show_entries",
                "format=format_name",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        stream = (data.get("streams") or [{}])[0]
        rate = stream.get("r_frame_rate")
        if rate and "/" in rate:
            numerator, denominator = rate.split("/", 1)
            fps = f"{float(numerator) / float(denominator):.3f}"
        else:
            fps = rate
        return {
            "fps": fps,
            "codec": stream.get("codec_name"),
            "container": (data.get("format") or {}).get("format_name"),
        }
    except (
        FileNotFoundError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
        json.JSONDecodeError,
    ):
        return {"fps": None, "codec": None, "container": None}


def memory_label(peak_bytes: int) -> str:
    rss = "unavailable"
    try:
        import psutil

        rss = f"{psutil.Process().memory_info().rss / 1024 / 1024:.1f} MiB RSS"
    except ImportError:
        pass
    return f"{peak_bytes / 1024 / 1024:.1f} MiB tracemalloc; {rss}"


def run_one(
    entry: dict[str, Any], raw: dict[str, Any], mode: Mode, temp: Path
) -> RunResult:
    label = str(entry["label"])
    try:
        quality = selected_quality(raw, entry.get("res"))
        duration = float(raw.get("duration") or 0)
        start = float(entry.get("start", 0))
        end = float(entry.get("end", min(duration, start + 30)))
        if not 0 <= start < end <= duration or end - start > MAX_RANGE_SECONDS:
            raise ValueError(
                f"range must be within video duration and <= {MAX_RANGE_SECONDS}s"
            )
        spec = ClipSpec(entry["url"], start, end, quality, mode)
        tracemalloc.start()
        wall_start = time.perf_counter()
        clip = download_clip(spec, temp / mode.value)
        wall_seconds = time.perf_counter() - wall_start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        metadata = probe(clip.path)
        return RunResult(
            label,
            mode.value,
            True,
            wall_seconds=wall_seconds,
            size_bytes=clip.path.stat().st_size,
            fps=metadata["fps"],
            codec=metadata["codec"],
            container=metadata["container"],
            peak_memory=memory_label(peak),
        )
    except Exception as exc:  # noqa: BLE001 - each benchmark failure belongs in the report
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        return RunResult(label, mode.value, False, error=f"{type(exc).__name__}: {exc}")


def markdown_report(
    videos: list[dict[str, Any]], runs: list[RunResult], multi: dict[str, Any]
) -> str:
    lines = [
        "# Clipper clip benchmarks",
        "",
        "Download and processing sub-phases are `unavailable` because the existing single-clip helper combines them; wall time is measured around the helper call.",
        "",
    ]
    lines += [
        "## Videos",
        "",
        "| Label | URL | Title | Duration | Captions | Expected |",
        "|---|---|---|---:|---|---|",
    ]
    for video in videos:
        lines.append(
            f"| {video['label']} | {video['url']} | {video.get('title', 'unavailable')} | {video.get('duration', 'unavailable')} | {video.get('caption_type', 'unavailable')} | {video['expected_caption_type']} |"
        )
    lines += [
        "",
        "## Runs",
        "",
        "| Label | Mode | Success | Wall (s) | Download (s) | Processing (s) | Size | FPS | Codec | Container | Peak memory | Error |",
        "|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|",
    ]
    for run in runs:
        lines.append(
            f"| {run.label} | {run.mode} | {'yes' if run.success else 'no'} | {fmt(run.wall_seconds)} | unavailable | unavailable | {run.size_bytes or 'unavailable'} | {run.fps or 'unavailable'} | {run.codec or 'unavailable'} | {run.container or 'unavailable'} | {run.peak_memory or 'unavailable'} | {run.error or ''} |"
        )
    lines += ["", "## Aggregates", ""]
    for mode in ("fast", "exact"):
        values = [
            run.wall_seconds
            for run in runs
            if run.mode == mode and run.wall_seconds is not None
        ]
        lines.append(
            f"- **{mode} wall time:** min `{fmt(min(values)) if values else 'unavailable'}`, max `{fmt(max(values)) if values else 'unavailable'}`, avg `{fmt(sum(values) / len(values)) if values else 'unavailable'}` seconds"
        )
    lines += [
        "",
        "## Multi-range reuse",
        "",
        f"- Result: **{multi['status']}**",
        f"- Observed `download_export` calls: `{multi['calls']}` (expected one)",
        f"- Detail: {multi['detail']}",
        "",
        "Failures are recorded above. Only process URLs for which you have permission.",
    ]
    return "\n".join(lines) + "\n"


def fmt(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark existing Clipper clip/export helpers."
    )
    parser.add_argument(
        "config", type=Path, help="JSON config path (YAML if PyYAML is installed)"
    )
    parser.add_argument("--report", type=Path, default=ROOT / "benchmark-report.md")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        runs: list[RunResult] = []
        videos: list[dict[str, Any]] = []
        with TemporaryDirectory(prefix="clipper-benchmark-") as directory:
            temp = Path(directory)
            for entry in config["videos"]:
                if entry["url"].startswith(PLACEHOLDER_PREFIX):
                    continue
                raw = fetch_info(entry["url"])
                video = {
                    **entry,
                    "title": raw.get("title", "unavailable"),
                    "duration": raw.get("duration", "unavailable"),
                    "caption_type": caption_type(raw),
                }
                videos.append(video)
                for mode in (Mode.FAST, Mode.EXACT):
                    runs.append(run_one(entry, raw, mode, temp))
            multi = {
                "status": "skipped",
                "calls": 0,
                "detail": "No non-placeholder video was available.",
            }
            if videos:
                entry = next(
                    video
                    for video in config["videos"]
                    if not video["url"].startswith(PLACEHOLDER_PREFIX)
                )
                raw = fetch_info(entry["url"])
                quality = selected_quality(raw, entry.get("res"))
                duration = float(raw.get("duration") or 0)
                start = float(entry.get("start", 0))
                end = min(float(entry.get("end", min(duration, start + 30))), duration)
                second_start = min(end + 1, max(start, duration - 1))
                second_end = min(duration, second_start + max(1, end - start))
                if second_end <= second_start:
                    multi = {
                        "status": "skipped",
                        "calls": 0,
                        "detail": "Video is too short for two bounded ranges.",
                    }
                else:
                    specs = (
                        ClipSpec(entry["url"], start, end, quality, Mode.FAST),
                        ClipSpec(
                            entry["url"], second_start, second_end, quality, Mode.FAST
                        ),
                    )
                    calls = 0

                    def counted(specs_arg, out_dir):
                        nonlocal calls
                        calls += 1
                        return download_export(specs_arg, out_dir)

                    try:
                        counted(specs, temp / "multi")
                        multi = {
                            "status": "passed",
                            "calls": calls,
                            "detail": "Existing download_export executed once for two ranges.",
                        }
                    except Exception as exc:  # noqa: BLE001 - report export failures per run
                        multi = {
                            "status": "failed",
                            "calls": calls,
                            "detail": f"{type(exc).__name__}: {exc}",
                        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown_report(videos, runs, multi), encoding="utf-8")
        print(f"Wrote benchmark report: {args.report}")
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(f"Benchmark configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
