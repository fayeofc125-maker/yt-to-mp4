import pytest
from pydantic import ValidationError

from app.schemas import ClipRequest, ExportRequest

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def make(**overrides):
    return ClipRequest(**{"url": URL, "start": 10, "end": 20, "res": 1080, **overrides})


def test_valid_request_defaults_to_exact_cut():
    assert make().mode == "exact"


@pytest.mark.parametrize("url", ["https://youtu.be/dQw4w9WgXcQ", "https://m.youtube.com/watch?v=x"])
def test_accepts_youtube_hosts(url):
    assert make(url=url).url == url


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "https://example.com/v.mp4", "https://youtube.com.evil.io/x"]
)
def test_rejects_other_sources(url):
    with pytest.raises(ValidationError):
        make(url=url)


@pytest.mark.parametrize(("start", "end"), [(20, 20), (20, 10)])
def test_rejects_empty_or_backwards_ranges(start, end):
    with pytest.raises(ValidationError):
        make(start=start, end=end)


@pytest.mark.parametrize(("res", "longest"), [(2160, 600), (1080, 3600), (720, 10800)])
def test_length_limit_depends_on_quality(res, longest):
    assert make(res=res, start=0, end=longest).end == longest
    with pytest.raises(ValidationError, match="shorter part or a lower quality"):
        make(res=res, start=0, end=longest + 1)


def test_export_ranges_are_merged_and_total_is_capped():
    request = ExportRequest(
        url=URL,
        res=1080,
        ranges=[{"start": 5, "end": 10}, {"start": 1, "end": 6}],
    )
    assert [(item.start, item.end) for item in request.ranges] == [(1, 10)]
    with pytest.raises(ValidationError, match="combined export duration"):
        ExportRequest(
            url=URL,
            res=720,
            ranges=[{"start": index * 2000, "end": index * 2000 + 1000} for index in range(20)],
        )


def test_export_rejects_non_finite_ranges():
    with pytest.raises(ValidationError, match="finite"):
        ExportRequest(url=URL, res=1080, ranges=[{"start": float("inf"), "end": 1}])
