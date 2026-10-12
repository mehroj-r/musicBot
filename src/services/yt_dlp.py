import asyncio
import os
import yt_dlp

from config import settings
from config.logging_conf import logger
from core.templates import AudioMetadata
from services.download.base import BaseDownloadService


class DLPService(BaseDownloadService):
    cookies_file = settings.COOKIES_FILE
    extra_kwargs = {}

    if cookies_file and os.path.exists(cookies_file):
        extra_kwargs['cookiefile'] = cookies_file
        logger.info(f"Using cookies file: {cookies_file}")

    @classmethod
    async def download_audio(cls, url: str, work_dir: str) -> tuple[AudioMetadata, str]:

        ydl_opts_audio = {
            'format': 'bestaudio/best',
            'quiet': True,
            # Links copied from a playlist or Mix carry &list=...; only fetch the linked video
            'noplaylist': True,
            'playlist_items': '1',
            'outtmpl': os.path.join(work_dir, 'audio.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            **cls.extra_kwargs
        }

        def download_audio():
            logger.info("Downloading audio ...")

            try:
                # One extraction gives both the metadata and the download
                with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                    info = ydl.extract_info(url, download=True)
            except Exception as e:
                logger.error(f"Failed to download audio: {str(e)}")
                raise

            if info.get('_type', 'video') != 'video':
                raise yt_dlp.utils.DownloadError("Unsupported URL: playlists are not supported")

            return info

        # Run in thread pool to avoid blocking
        info = await asyncio.to_thread(download_audio)
        file_path = info['requested_downloads'][0]['filepath']
        logger.info(f"Audio downloaded successfully to {file_path}")

        metadata = AudioMetadata(
            artist=info.get('uploader') or 'Unknown Artist',
            title=info.get('title') or 'Unknown Title',
            duration=int(info['duration']) if info.get('duration') else None,
            thumbnail_url=info.get('thumbnail'),
        )
        return metadata, file_path
