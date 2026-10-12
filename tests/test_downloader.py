from pathlib import Path

import pytest
from yt_dlp.utils import DownloadError

from musicbot.config import AudioFormat
from musicbot.services.downloader import (
    DownloadedTrack,
    Downloader,
    DownloadRejected,
    Track,
    describe_error,
    progress_hooks,
    safe_filename,
    track_from_info,
)

VIDEO = {"_type": "video", "extractor_key": "Youtube", "id": "abc123", "duration": 213}


def test_safe_filename_replaces_path_separators():
    assert "/" not in safe_filename("AC/DC - Back In Black")


def test_safe_filename_truncates_multibyte_titles_by_bytes():
    name = safe_filename("Песня " * 100)
    assert len(name.encode()) <= 200
    name.encode().decode()  # still valid UTF-8


def test_safe_filename_never_empty():
    assert safe_filename("   ") == "audio"


def test_track_prefers_music_metadata():
    info = {**VIDEO, "title": "Official video", "track": "Song", "artists": ["A", "B"]}
    track = track_from_info(info)
    assert (track.title, track.artist) == ("Song", "A, B")


def test_track_strips_artist_prefix_from_title():
    info = {**VIDEO, "title": "Rick Astley - Never Gonna Give You Up", "uploader": "Rick Astley"}
    track = track_from_info(info)
    assert (track.title, track.artist) == ("Never Gonna Give You Up", "Rick Astley")


def test_track_keeps_title_when_prefix_is_not_the_artist():
    info = {**VIDEO, "title": "Intro - Live", "uploader": "Some Channel"}
    assert track_from_info(info).title == "Intro - Live"


def test_track_drops_topic_suffix():
    info = {**VIDEO, "title": "Song", "uploader": "Band - Topic"}
    assert track_from_info(info).artist == "Band"


def test_file_name_combines_artist_and_title(tmp_path: Path):
    track = Track("Youtube", "abc", "Back In Black", "AC/DC", 254, "")
    audio = DownloadedTrack(track, AudioFormat.M4A, tmp_path / "audio.m4a", None, None)
    assert audio.file_name.endswith(" - Back In Black.m4a")
    assert "/" not in audio.file_name


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (DownloadError("ERROR: [youtube] x: This video is unavailable"), "unavailable"),
        (DownloadError("ERROR: Private video. Sign in"), "private"),
        (DownloadError("Sign in to confirm you're not a bot"), "blocking"),
        (DownloadError("Incomplete YouTube ID x. URL looks truncated."), "incomplete"),
        (DownloadError("Unsupported URL: https://example.com"), "not supported"),
        (DownloadError("No suitable extractor found for URL https://x.y"), "not supported"),
        (DownloadRejected("Custom reason."), "Custom reason."),
        (RuntimeError("boom"), "Something went wrong"),
    ],
)
def test_describe_error(error, expected):
    assert expected in describe_error(error)


@pytest.mark.parametrize(
    ("info", "reason"),
    [
        ({**VIDEO, "_type": "playlist"}, "Playlists"),
        ({**VIDEO, "live_status": "is_live"}, "Live streams"),
        ({**VIDEO, "duration": 3 * 3600 + 1}, "longer than 180 minutes"),
    ],
)
def test_rejects_unsuitable_links(info, reason):
    with pytest.raises(DownloadRejected, match=reason):
        Downloader(None, max_duration_minutes=180)._check(info)


def test_accepts_regular_video():
    Downloader(None, max_duration_minutes=180)._check(VIDEO)


def test_each_job_gets_its_own_cookies_copy(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    work_dir = tmp_path / "job"
    work_dir.mkdir()

    options = Downloader(cookies, 180)._options(work_dir, AudioFormat.M4A)

    assert options["cookiefile"] == str(work_dir / "cookies.txt")
    assert (work_dir / "cookies.txt").read_text() == cookies.read_text()


def test_missing_cookies_file_is_ignored(tmp_path: Path):
    downloader = Downloader(tmp_path / "missing.txt", 180)
    assert "cookiefile" not in downloader._options(tmp_path, AudioFormat.M4A)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", ("Youtube", "dQw4w9WgXcQ")),
        ("https://youtu.be/dQw4w9WgXcQ?si=share", ("Youtube", "dQw4w9WgXcQ")),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", ("Youtube", "dQw4w9WgXcQ")),
        ("https://www.youtube.com/shorts/aqz-KE-bpKQ", ("Youtube", "aqz-KE-bpKQ")),
        # From a Mix: only the video is downloaded, so it's the video's key
        (
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ&start_radio=1",
            ("Youtube", "dQw4w9WgXcQ"),
        ),
        ("https://soundcloud.com/forss/flickermood", None),
        ("https://example.com/page", None),
    ],
)
def test_identify_without_network(url, expected):
    assert Downloader(None, 180).identify(url) == expected


def test_progress_hooks_report_stages():
    reports = []
    on_download, on_postprocess = (
        hooks[0] for hooks in progress_hooks(lambda *r: reports.append(r))
    )

    on_download({"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100})
    on_download({"status": "downloading", "downloaded_bytes": 25, "total_bytes_estimate": 50})
    on_download({"status": "downloading", "downloaded_bytes": 25})
    on_download({"status": "finished", "downloaded_bytes": 100})
    on_postprocess({"status": "started", "postprocessor": "ExtractAudio"})
    on_postprocess({"status": "started", "postprocessor": "MoveFiles"})

    assert reports == [("download", 0.25), ("download", 0.5), ("download", None), ("convert", None)]
