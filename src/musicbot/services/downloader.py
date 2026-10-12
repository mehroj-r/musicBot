import asyncio
import logging
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.extractor import gen_extractor_classes
from yt_dlp.utils import DownloadError, sanitize_filename

from musicbot.config import AudioFormat
from musicbot.services.media import make_artwork, write_tags
from musicbot.services.yandex import YandexAuth, YandexMusicIE

logger = logging.getLogger(__name__)

FORMAT_SELECTORS = {
    # Prefer an AAC stream (YouTube's, Yandex Music's) so the M4A is remuxed, not re-encoded
    AudioFormat.M4A: "bestaudio[ext=m4a]/bestaudio/best",
    # Likewise an MP3 where the site has one (Yandex Music, SoundCloud)
    AudioFormat.MP3: "bestaudio[ext=mp3]/bestaudio/best",
}

YANDEX_MUSIC_LINK = re.compile(r"https?://music\.yandex\.[a-z]+/", re.IGNORECASE)


# Called from yt-dlp's worker thread with the stage ("download" or "convert") and,
# while downloading, the fraction done when the size is known
ProgressCallback = Callable[[str, float | None], None]


class YtDlpLogger:
    """
    Routes yt-dlp output into logging. Errors become exceptions that callers report.
    """

    def debug(self, message: str) -> None:
        logger.debug(message)

    def info(self, message: str) -> None:
        logger.debug(message)

    def warning(self, message: str) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.debug(message)


class DownloadRejected(Exception):
    """
    The link can't be downloaded; the message is safe to show to the user.
    """


@dataclass(frozen=True)
class Track:
    source: str
    source_id: str
    title: str
    artist: str
    duration: int | None
    webpage_url: str


@dataclass(frozen=True)
class DownloadedTrack:
    track: Track
    audio_format: AudioFormat
    audio_path: Path
    cover_path: Path | None
    thumbnail_path: Path | None

    @property
    def size(self) -> int:
        return self.audio_path.stat().st_size

    @property
    def file_name(self) -> str:
        """
        File name users see when they save the audio from Telegram.
        """
        return f"{safe_filename(f'{self.track.artist} - {self.track.title}')}.{self.audio_format}"


def safe_filename(name: str, max_bytes: int = 200) -> str:
    """
    Make a file name (without extension) safe for any filesystem, truncated by bytes so
    multibyte titles stay under the 255-byte name limit.
    """
    cleaned = sanitize_filename(name).strip()
    truncated = cleaned.encode()[:max_bytes].decode(errors="ignore").strip()
    return truncated or "audio"


def track_from_info(info: dict[str, Any]) -> Track:
    """
    Pick the most music-like title and artist yt-dlp found for the video.
    """
    artists = info.get("artists") or ([info["artist"]] if info.get("artist") else [])
    if artists:
        artist = ", ".join(artists)
    else:
        uploader = info.get("creator") or info.get("uploader") or info.get("channel")
        artist = (uploader or "Unknown artist").removesuffix(" - Topic")

    title = info.get("track")
    if not title:
        title = info.get("title") or "Unknown title"
        # "Rick Astley - Never Gonna Give You Up" uploaded by "Rick Astley"
        prefix, separator, rest = title.partition(" - ")
        if separator and rest and prefix.casefold() == artist.casefold():
            title = rest

    duration = info.get("duration")
    return Track(
        source=info["extractor_key"],
        source_id=str(info["id"]),
        title=title,
        artist=artist,
        duration=int(duration) if duration else None,
        webpage_url=info.get("webpage_url") or info.get("original_url") or "",
    )


def describe_error(error: Exception) -> str:
    """
    Turn a download failure into a message that can be shown to the user.
    """
    if isinstance(error, DownloadRejected):
        return str(error)
    if not isinstance(error, DownloadError):
        return "Something went wrong while downloading."

    message = str(error).lower()
    known_errors = [
        ("private video", "This video is private."),
        ("confirm your age", "This video is age-restricted."),
        ("not a bot", "YouTube is blocking the server right now. Please try again later."),
        (
            "no longer accepts the bot's sign-in",
            "Yandex Music no longer accepts the bot's sign-in. An admin needs to sign in again "
            "with /yandex.",
        ),
        ("30-second preview", "Yandex Music only gives the bot a 30-second preview of this track."),
        ("isn't available on yandex music", "This track isn't available on Yandex Music."),
        ("not available in your country", "This video is not available in the server's region."),
        ("live event", "Live streams can't be downloaded."),
        ("unsupported url", "This link is not supported."),
        ("no suitable extractor", "This link is not supported."),
        ("looks truncated", "This link looks incomplete. Please copy it again."),
        ("unavailable", "This video is unavailable."),
    ]
    for needle, reply in known_errors:
        if needle in message:
            return reply
    return "Could not download this link."


def progress_hooks(on_progress: ProgressCallback) -> tuple[list, list]:
    """
    Translate yt-dlp's download and post-processing hooks into ``on_progress`` calls.
    """

    def on_download(status: dict[str, Any]) -> None:
        if status["status"] == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            on_progress("download", status["downloaded_bytes"] / total if total else None)

    def on_postprocess(status: dict[str, Any]) -> None:
        if status["status"] == "started" and status["postprocessor"] == "ExtractAudio":
            on_progress("convert", None)

    return [on_download], [on_postprocess]


class Downloader:
    def __init__(
        self,
        cookies_file: Path | None,
        max_duration_minutes: int,
        yandex: YandexAuth | None = None,
    ) -> None:
        self.cookies_file = cookies_file
        self.max_duration = max_duration_minutes * 60
        self.yandex = yandex
        # The same extractors downloads use: ours for Yandex Music instead of yt-dlp's
        self._extractors = [
            YandexMusicIE,
            *(
                ie
                for ie in gen_extractor_classes()
                if ie.ie_key() != "Generic" and not ie.IE_NAME.startswith("yandexmusic:")
            ),
        ]

        if cookies_file and not (cookies_file.is_file() and os.access(cookies_file, os.R_OK)):
            logger.warning("Cookies file %s is missing or unreadable; ignoring it", cookies_file)
            self.cookies_file = None

    def identify(self, url: str) -> tuple[str, str] | None:
        """
        Work out which track a link points to without any network request, the way yt-dlp
        checks its download archive. Not every site allows this.

        :return: The extractor key and track ID, matching ``Track.source`` and ``source_id``.
        """
        extractor = next((ie for ie in self._extractors if ie.suitable(url)), None)
        if extractor is None:
            return None
        source, source_id = extractor.ie_key(), extractor.get_temp_id(url)

        # A watch link inside a playlist or Mix: with noplaylist only the video is downloaded
        if source == "YoutubeTab":
            video_ids = parse_qs(urlparse(url).query).get("v")
            source, source_id = ("Youtube", video_ids[0]) if video_ids else (source, None)

        return (source, source_id) if source_id else None

    async def download(
        self,
        url: str,
        work_dir: Path,
        audio_format: AudioFormat,
        on_progress: ProgressCallback | None = None,
    ) -> DownloadedTrack:
        """
        Download the audio behind ``url`` into ``work_dir`` and tag it.
        The caller owns ``work_dir`` and removes it afterwards.
        """
        yandex_token = await self._yandex_token(url)
        info = await asyncio.to_thread(
            self._download, url, work_dir, audio_format, on_progress, yandex_token
        )
        track = track_from_info(info)
        audio_path = Path(info["requested_downloads"][0]["filepath"])

        def finish() -> tuple[Path | None, Path | None]:
            cover_path, thumbnail_path = None, None
            source = next(work_dir.glob("cover-source.*"), None)
            if source:
                try:
                    cover_path, thumbnail_path = make_artwork(source, work_dir)
                except OSError as e:
                    # A broken thumbnail must not fail the download
                    logger.warning("Continuing without cover art: %s", e)
            write_tags(audio_path, audio_format, track.title, track.artist, cover_path)
            return cover_path, thumbnail_path

        cover_path, thumbnail_path = await asyncio.to_thread(finish)
        return DownloadedTrack(track, audio_format, audio_path, cover_path, thumbnail_path)

    async def _yandex_token(self, url: str) -> str | None:
        """
        The token to download a Yandex Music link with; None for other links.
        """
        if not YANDEX_MUSIC_LINK.match(url):
            return None
        if not YandexMusicIE.suitable(url):
            raise DownloadRejected(
                "Only single tracks can be downloaded from Yandex Music. Send a link to a track."
            )
        token = await self.yandex.token() if self.yandex else None
        if token is None:
            raise DownloadRejected(
                "Yandex Music isn't set up yet: an admin needs to sign in with /yandex."
            )
        return token

    def _download(
        self,
        url: str,
        work_dir: Path,
        audio_format: AudioFormat,
        on_progress: ProgressCallback | None,
        yandex_token: str | None = None,
    ) -> dict[str, Any]:
        options = self._options(work_dir, audio_format)
        if on_progress:
            options["progress_hooks"], options["postprocessor_hooks"] = progress_hooks(on_progress)
        if yandex_token:
            options["extractor_args"] = {"yandexmusic": {"token": [yandex_token]}}

        with YoutubeDL(options) as ydl:
            ydl.add_info_extractor(YandexMusicIE())
            # Check the metadata first, then download from the same extraction
            info = ydl.extract_info(url, download=False)
            self._check(info)
            return ydl.process_ie_result(info, download=True)

    def _check(self, info: dict[str, Any]) -> None:
        if info.get("_type", "video") != "video":
            raise DownloadRejected("Playlists aren't supported. Send a link to a single track.")
        if info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
            raise DownloadRejected("Live streams can't be downloaded.")
        duration = info.get("duration")
        if duration and duration > self.max_duration:
            raise DownloadRejected(
                f"This is longer than {self.max_duration // 60} minutes, the limit for downloads."
            )

    def _options(self, work_dir: Path, audio_format: AudioFormat) -> dict[str, Any]:
        options: dict[str, Any] = {
            "format": FORMAT_SELECTORS[audio_format],
            "logger": YtDlpLogger(),
            "noprogress": True,
            # Links copied from a playlist or Mix carry &list=...; only fetch the linked video
            "noplaylist": True,
            # Don't resolve every entry of a playlist link just to refuse it
            "extract_flat": "in_playlist",
            # Named sites only: the generic extractor would fetch arbitrary URLs. yt-dlp's
            # Yandex Music extractors use a web API that no longer works; ours is added instead
            "allowed_extractors": ["default", "-generic", "-yandexmusic:.*"],
            "outtmpl": {
                "default": str(work_dir / "audio.%(ext)s"),
                "thumbnail": str(work_dir / "cover-source.%(ext)s"),
            },
            "writethumbnail": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": str(audio_format),
                    # Only applies when the audio has to be re-encoded, e.g. a Yandex Music
                    # track that only exists as MP3 for an M4A user
                    "preferredquality": "192",
                }
            ],
        }
        if self.cookies_file:
            # yt-dlp writes cookies back on exit; give every job its own copy
            job_cookies = work_dir / "cookies.txt"
            shutil.copyfile(self.cookies_file, job_cookies)
            options["cookiefile"] = str(job_cookies)
        return options
