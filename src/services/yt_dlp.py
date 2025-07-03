import asyncio
import os
import uuid
from typing import Dict, Tuple

import aiohttp
import yt_dlp
from mutagen.id3 import TIT2, TPE1, APIC
from mutagen.mp3 import MP3

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

        # Unique filename generation
        filename = valid_filename(str(uuid.uuid4().hex))

        # Prepare paths
        download_dir = os.getcwd() + "/tmp"
        file_path = f"{download_dir}/{filename}.mp3"
        thumbnail_path = f"{download_dir}/{filename}_thumbnail.jpg"

        # Ensure the download directory exists
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        # Run thumbnail and audio downloads concurrently
        audio_download_task = asyncio.create_task(
            cls._download_audio_file(url=url, save_path=file_path)
        )

        audio_info = await cls._get_audio_info(url=url)
        uploader = audio_info.get('uploader', 'Unknown Artist')
        audio_title = audio_info.get('title', 'Unknown Title')
        new_path = f"{download_dir}/{valid_filename(audio_title)}.mp3"

        thumbnail_url = audio_info.get('thumbnail', None)
        if not thumbnail_url:
            logger.warning("No thumbnail found, using default placeholder.")
            thumbnail_url = "https://www.creativefabrica.com/wp-content/uploads/2023/08/21/Audio-Sound-Music-Frequency-Logo-Graphics-77376936-1-1-580x387.jpg"

        await cls._download_thumbnail(thumbnail_url=thumbnail_url, save_path=thumbnail_path)

        # Wait for audio download to complete
        await audio_download_task

        # Rename file
        os.rename(file_path, new_path)

        # Process audio file after downloads complete
        await cls._process_audio_file(
            file_path=new_path,
            thumbnail_path=thumbnail_path,
            artist=uploader,
            title=audio_title,
        )

        data = {
            "artist": uploader,
            "title": audio_title
        }

        return new_path, thumbnail_path, audio_title, data

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
        return info

    @classmethod
    async def _download_thumbnail(cls, thumbnail_url: str, save_path: str) -> None:
        """
        Download the thumbnail image from the given URL using async HTTP client.
        """
        logger.info("Downloading thumbnail ...")
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
        except Exception as e:
            logger.error(f"Failed to download thumbnail: {str(e)}")
            raise
        logger.info(f"Thumbnail successfully downloaded to {save_path}")

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

    @classmethod
    async def _process_audio_file(cls, file_path: str, thumbnail_path: str, artist: str, title: str) -> None:
        """
        Add metadata and cover art to audio file without re-encoding.
        Uses mutagen for direct ID3 tag manipulation.
        """
        logger.info("Adding metadata to audio file ...")

        def add_metadata():
            try:
                # Load the MP3 file
                audio_file = MP3(file_path)

                # Create ID3 tags if they don't exist
                if audio_file.tags is None:
                    audio_file.add_tags()

                # Add basic metadata
                audio_file.tags.add(TIT2(encoding=3, text=title))  # Title
                audio_file.tags.add(TPE1(encoding=3, text=artist))  # Artist

                # Add cover art if thumbnail exists
                if os.path.exists(thumbnail_path):
                    with open(thumbnail_path, 'rb') as albumart:
                        audio_file.tags.add(
                            APIC(
                                encoding=3,                # UTF-8
                                mime='image/jpeg',         # MIME type
                                type=3,                    # Cover (front)
                                desc='Cover',
                                data=albumart.read()
                            )
                        )

                # Save the changes
                audio_file.save()
                logger.info(f"Metadata added successfully to {file_path}")

            except Exception as e:
                logger.error(f"Failed to add metadata: {str(e)}")
                raise

        # Run in thread pool to avoid blocking
        await asyncio.to_thread(add_metadata)