"""How much video one clip may contain, by quality. Higher quality costs more, so it gets less."""

MAX_RESOLUTION = 2160  # 8K is deliberately not offered on the site

# (minimum short-side resolution, longest clip in seconds); the first matching row wins.
_CAPS = [(2160, 10 * 60), (1440, 30 * 60), (1080, 60 * 60), (0, 3 * 60 * 60)]


def max_clip_seconds(res: int) -> int:
    return next(seconds for min_res, seconds in _CAPS if res >= min_res)
