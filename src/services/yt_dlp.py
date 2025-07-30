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
    async def get_audio_details(cls, url: str) -> AudioMetadata:

        ydl_opts_info = {
            'skip_download': True,
            'quiet': True,
            'extract_flat': 'in_playlist',
            **cls.extra_kwargs
        }

        def extract_info():

            logger.info("Extracting audio details ...")

            try:
                with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as e:
                logger.error(f"Failed to extract audio details: {str(e)}")
                raise

        # Run in thread pool to avoid blocking
        info = await asyncio.to_thread(extract_info)
        logger.info("Audio details extracted successfully")

        artist = info.get('uploader', 'Unknown Artist')
        title = info.get('title', 'Unknown Title')
        thumbnail_url = info.get('thumbnail', None)

        return AudioMetadata(artist=artist, title=title, thumbnail_url=thumbnail_url)

    @classmethod
    async def download_audio(cls, url: str, save_path: str) -> None:

        ydl_opts_audio = {
            'format': 'bestaudio/best',
            'quiet': True,
            'outtmpl': save_path.rstrip('.mp3'),
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
                with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                    ydl.download([url])
            except Exception as e:
                logger.error(f"Failed to download audio: {str(e)}")
                raise

            logger.info(f"Audio downloaded successfully to {save_path}")

        # Run in thread pool to avoid blocking
        await asyncio.to_thread(download_audio)