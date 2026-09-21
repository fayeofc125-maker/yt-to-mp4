import pytest

from app.limits import max_clip_seconds


@pytest.mark.parametrize(
    ("res", "minutes"),
    [(2160, 10), (1440, 30), (1080, 60), (720, 180), (144, 180), (1439, 60), (4320, 10)],
)
def test_higher_quality_gets_shorter_clips(res, minutes):
    assert max_clip_seconds(res) == minutes * 60
