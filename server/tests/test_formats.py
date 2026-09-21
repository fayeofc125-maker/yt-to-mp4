from app.formats import Quality, build_qualities


def video(width, height, fps=30, **extra):
    return {"vcodec": "vp9", "width": width, "height": height, "fps": fps, **extra}


def test_menu_is_capped_at_what_the_video_has():
    formats = [video(1280, 720), video(1920, 1080)]
    assert [q.label for q in build_qualities(formats)] == ["1080p", "720p"]


def test_names_and_one_entry_per_resolution():
    formats = [
        video(3840, 2160),
        video(2560, 1440),
        video(1920, 1080),
        video(1920, 1080, fps=60),  # same resolution at another frame rate: still one entry
    ]
    assert [q.label for q in build_qualities(formats)] == ["4K (2160p)", "2K (1440p)", "1080p"]


def test_duplicate_codecs_collapse_and_non_video_is_ignored():
    formats = [
        video(1920, 1080),
        {**video(1920, 1080), "vcodec": "avc1"},
        {"vcodec": "none", "acodec": "opus"},  # audio only
        {"vcodec": "none", "width": 160, "height": 90},  # storyboard
    ]
    assert build_qualities(formats) == [Quality(1080)]


def test_vertical_video_is_labelled_by_short_side():
    assert build_qualities([video(1080, 1920)]) == [Quality(1080)]


def test_bitrate_is_best_video_plus_best_audio():
    formats = [
        video(1920, 1080, tbr=4000),
        video(1920, 1080, fps=60, tbr=6000),  # the frame rate that will actually be downloaded
        {"vcodec": "none", "acodec": "opus", "abr": 128},
        {"vcodec": "none", "acodec": "opus", "abr": 160},
    ]
    assert build_qualities(formats)[0].kbps == 6160


def test_8k_is_not_offered():
    assert [q.res for q in build_qualities([video(7680, 4320), video(3840, 2160)])] == [2160]
