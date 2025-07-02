import asyncio
import os
from typing import Dict, Tuple

import aiohttp
import pydub
import yt_dlp

from config import settings
from config.logging_config import logger
from utils.dlp_utils import valid_filename


class DLPService:
    cookies_file = settings.COOKIES_FILE
    extra_kwargs = { }

    @classmethod
    async def download_audio(cls, url: str) -> Tuple[str, str, str, Dict[str, str]]:

        if cls.cookies_file and os.path.exists(cls.cookies_file):
            cls.extra_kwargs['cookiefile'] = cls.cookies_file
            logger.info(f"Using cookies file: {cls.cookies_file}")

        # Use yt_dlp Python API to extract video info and download audio
        logger.info("Extracting audio details ...")

        # Get audio information without downloading for display purposes
        audio_info = await cls._get_audio_info(url)

        audio_title = audio_info.get('title', 'audio')
        uploader = audio_info.get('uploader', 'unknown')
        audio_thumbnail = audio_info.get('thumbnail', None)
        filename = valid_filename(audio_title)[:250]

        # Prepare paths
        download_dir = os.getcwd() + "/tmp"
        file_path = f"{download_dir}/{filename}.mp3"
        thumbnail_path = f"{download_dir}/thumbnail.jpg"

        # Ensure the download directory exists
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        # Ensure the audio thumbnail URL is available
        if not audio_thumbnail:
            raise ValueError("No thumbnail URL found in audio info.")

        # Run thumbnail and audio downloads concurrently
        logger.info("Starting concurrent downloads ...")
        download_tasks = [
            cls._download_thumbnail(thumbnail_url=audio_thumbnail, save_path=thumbnail_path),
            cls._download_audio_file(url=url, save_path=file_path)
        ]

        await asyncio.gather(*download_tasks)

        # Process audio file after downloads complete
        await cls._process_audio_file(
            file_path=file_path,
            thumbnail_path=thumbnail_path,
            artist=uploader,
            title=audio_title
        )

        data = {
            "artist": uploader,
            "title": audio_title
        }

        return file_path, thumbnail_path, audio_title, data

    @classmethod
    async def _get_audio_info(cls, url: str) -> Dict[str, str]:
        """
        Extract audio information without downloading.
        """
        ydl_opts_info = {
            'skip_download': True,
            'quiet': True,
            'extract_flat': 'in_playlist',
            **cls.extra_kwargs
        }

        def extract_info():
            try:
                with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as e:
                logger.error(f"Failed to extract audio details: {str(e)}")
                raise

        # Run in thread pool to avoid blocking
        info = await asyncio.to_thread(extract_info)
        return info

    @classmethod
    async def _download_thumbnail(cls, thumbnail_url: str, save_path: str) -> None:
        """
        Download the thumbnail image from the given URL using async HTTP client.
        """
        logger.info(" - Downloading thumbnail ...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(thumbnail_url, allow_redirects=True) as response:
                    response.raise_for_status()
                    content = await response.read()

                    # Write file in thread pool to avoid blocking
                    await asyncio.to_thread(
                        cls._write_file,
                        save_path,
                        content
                    )
            logger.info(f"Thumbnail downloaded successfully to {save_path}")
        except Exception as e:
            logger.error(f"Failed to download thumbnail: {str(e)}")
            raise

    @staticmethod
    def _write_file(file_path: str, content: bytes) -> None:
        """Helper method to write file content."""
        with open(file_path, 'wb') as f:
            f.write(content)

    @classmethod
    async def _download_audio_file(cls, url: str, save_path: str) -> None:
        """
        Download audio file using yt_dlp in thread pool.
        """
        logger.info(" - Downloading audio ...")

        def download_audio():
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

            with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                ydl.download([url])

        # Run in thread pool to avoid blocking
        await asyncio.to_thread(download_audio)

    @classmethod
    async def _process_audio_file(cls, file_path: str, thumbnail_path: str, artist: str, title: str) -> None:
        """
        Process the audio file to add metadata and cover image in thread pool.
        """
        logger.info(" - Processing audio ...")

        def process_audio():
            tags = {
                "artist": artist,
                "title": title
            }
            export_kwargs = {
                "bitrate": "128k",
                "tags": tags,
                "format": 'mp3',
                "id3v2_version": '3'
            }
            if os.path.exists(thumbnail_path):
                export_kwargs["cover"] = thumbnail_path

            pydub.AudioSegment.from_file(file_path).export(
                file_path,
                **export_kwargs
            )

        # Run in thread pool to avoid blocking
        await asyncio.to_thread(process_audio)