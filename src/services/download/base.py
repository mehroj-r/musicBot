import asyncio
import os
import shutil
import tempfile
from abc import abstractmethod, ABC
from typing import final

import aiohttp
from mutagen.id3 import TIT2, TPE1, APIC
from mutagen.mp3 import MP3
from PIL import Image

from config.logging_conf import logger
from core.templates import AudioData, AudioMetadata
from utils.dlp_utils import safe_filename


class BaseDownloadService(ABC):
    """
    Base class for download services.
    """

    @classmethod
    @final
    async def download(cls, url: str) -> AudioData:
        """
        Download audio from the given URL into a fresh per-job directory.
        The caller owns the returned ``work_dir`` and must remove it when done.

        :param url: The URL of the audio.
        :return: The downloaded audio with its metadata.
        """
        work_dir = tempfile.mkdtemp(prefix="job-", dir=cls._get_download_root())

        try:
            # Download the audio and read its metadata from the same extraction
            audio_details, downloaded_path = await cls.download_audio(url=url, work_dir=work_dir)

            # Name the file after its title so it looks right once saved from Telegram
            audio_file_path = os.path.join(work_dir, f"{safe_filename(audio_details.title)}.mp3")
            os.rename(downloaded_path, audio_file_path)

            # Cover art is optional; a missing or broken thumbnail must not fail the download
            cover_path, thumbnail_path = None, None
            if audio_details.thumbnail_url:
                try:
                    cover_path, thumbnail_path = await cls.download_thumbnail(
                        thumbnail_url=audio_details.thumbnail_url,
                        work_dir=work_dir,
                    )
                except Exception as e:
                    logger.warning(f"Continuing without cover art: {e}")

            audio_data = AudioData(
                work_dir=work_dir,
                file_path=audio_file_path,
                cover_path=cover_path,
                thumbnail_path=thumbnail_path,
                **audio_details.model_dump(),
            )

            # Process the audio file to add metadata and cover art
            await cls.process_audio(audio_data=audio_data)
        except BaseException:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

        return audio_data

    @classmethod
    @final
    def _get_download_root(cls) -> str:
        download_dir = os.path.join(os.getcwd(), "tmp")
        os.makedirs(download_dir, exist_ok=True)
        return download_dir

    @classmethod
    @abstractmethod
    async def download_audio(cls, url: str, work_dir: str) -> tuple[AudioMetadata, str]:
        """
        Download the audio file from the given URL into ``work_dir`` as MP3.

        :param url: The URL of the audio.
        :param work_dir: The directory where the audio file will be saved.
        :return: The audio metadata and the path of the downloaded MP3 file.
        """
        pass

    @classmethod
    @final
    async def download_thumbnail(cls, thumbnail_url: str, work_dir: str) -> tuple[str, str]:
        """
        Download the thumbnail and derive a square JPEG cover and a Telegram-sized thumbnail.

        :return: Paths of the cover image and the 320x320 thumbnail.
        """
        logger.info("Downloading thumbnail ...")

        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url, allow_redirects=True) as response:
                response.raise_for_status()
                content = await response.read()

        source_path = os.path.join(work_dir, "thumbnail_source")
        cover_path = os.path.join(work_dir, "cover.jpg")
        thumbnail_path = os.path.join(work_dir, "thumbnail.jpg")

        def convert():
            cls._write_file(source_path, content)
            with Image.open(source_path) as image:
                # Center-crop to a square: YouTube art tracks put the album cover in the middle
                image = image.convert("RGB")
                side = min(image.size)
                left = (image.width - side) // 2
                top = (image.height - side) // 2
                square = image.crop((left, top, left + side, top + side))

                square.resize((min(side, 800),) * 2, Image.LANCZOS).save(cover_path, "JPEG", quality=90)
                # Telegram only accepts JPEG thumbnails up to 320x320 and 200 kB
                square.resize((320, 320), Image.LANCZOS).save(thumbnail_path, "JPEG", quality=85)

        # Decode and write images in thread pool to avoid blocking
        await asyncio.to_thread(convert)
        logger.info(f"Thumbnail successfully saved to {thumbnail_path}")

        return cover_path, thumbnail_path

    @classmethod
    @final
    async def process_audio(cls, audio_data: AudioData) -> None:
        """
        Add metadata and cover art to audio file without re-encoding.
        Uses mutagen for direct ID3 tag manipulation.
        """
        logger.info("Adding metadata to audio file ...")

        file_path = audio_data.file_path
        title = audio_data.title
        artist = audio_data.artist
        cover_path = audio_data.cover_path

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

                # Add cover art if it was downloaded
                if cover_path:
                    with open(cover_path, 'rb') as albumart:
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

    @staticmethod
    def _write_file(file_path: str, content: bytes) -> None:
        """Helper method to write file content."""
        with open(file_path, 'wb') as f:
            f.write(content)
