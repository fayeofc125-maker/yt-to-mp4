"""Turn raw yt-dlp format dicts into the quality menu shown to the user."""

from dataclasses import dataclass, field

from .limits import MAX_RESOLUTION

_NAMED = {4320: "8K", 2160: "4K", 1440: "2K"}


@dataclass(frozen=True, order=True)
class Quality:
    res: int  # short side in pixels, the way YouTube labels it (1080p, also for vertical video)
    kbps: int = field(
        default=0, compare=False
    )  # video plus best audio; only used for size estimates
    fps: float | None = field(default=None, compare=False)
    codec: str | None = field(default=None, compare=False)
    container: str | None = field(default=None, compare=False)
    has_audio: bool = field(default=False, compare=False)
    audio_available: bool = field(default=False, compare=False)
    format_id: str | None = field(default=None, compare=False)

    @property
    def label(self) -> str:
        return f"{_NAMED[self.res]} ({self.res}p)" if self.res in _NAMED else f"{self.res}p"


def build_qualities(formats: list[dict]) -> list[Quality]:
    """One entry per resolution that has a real video stream, best first."""
    video: dict[int, dict] = {}
    audio = 0.0
    for f in formats:
        if f.get("vcodec") in (None, "none"):
            if f.get("acodec") not in (None, "none"):
                audio = max(audio, f.get("abr") or f.get("tbr") or 0)
            continue  # audio-only streams and storyboards
        sides = [s for s in (f.get("width"), f.get("height")) if s]
        if sides and min(sides) <= MAX_RESOLUTION:
            res = min(sides)
            current = video.get(res)
            candidate_bitrate = f.get("tbr") or 0
            current_bitrate = current.get("tbr") or 0 if current else -1
            candidate_rank = (
                candidate_bitrate,
                f.get("fps") or 0,
                str(f.get("format_id") or ""),
            )
            current_rank = (
                (
                    current_bitrate,
                    current.get("fps") or 0,
                    str(current.get("format_id") or ""),
                )
                if current
                else None
            )
            if current is None or candidate_rank > current_rank:
                video[res] = f
    return sorted(
        (
            Quality(
                res,
                round((format_info.get("tbr") or 0) + audio),
                format_info.get("fps"),
                format_info.get("vcodec"),
                format_info.get("ext"),
                format_info.get("acodec") not in (None, "none"),
                audio > 0,
                format_info.get("format_id"),
            )
            for res, format_info in video.items()
        ),
        reverse=True,
    )
