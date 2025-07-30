import asyncio
import os
import uuid
from abc import abstractmethod, ABC
from typing import final

from aiogram.client.session import aiohttp
from mutagen.id3 import TIT2, TPE1, APIC
from mutagen.mp3 import MP3

from config.logging_conf import logger
from core.templates import AudioData, AudioMetadata
from utils.dlp_utils import valid_filename


class BaseDownloadService(ABC):
    """
    Base class for download services.
    """

    @classmethod
    @final
    async def download(cls, url: str, *args, **kwargs) -> AudioData:
        """
        Download audio from the given URL.

        :param url: The URL of the audio.
        :return: The path to the downloaded audio file.
        """

        # Generate save paths for audio and thumbnail
        audio_file_path = cls._get_audio_file_path()
        thumbnail_file_path = cls._get_thumbnail_file_path()

        # Initiate the audio download task
        audio_download_task = asyncio.create_task(
            cls.download_audio(url=url, save_path=audio_file_path)
        )

        # Retrieve audio details
        audio_details: AudioMetadata = await cls.get_audio_details(url=url)

        # Generate new file_path for audio
        new_audio_file_path = cls._get_audio_file_path(filename=audio_details.title)

        # Download the thumbnail if it exists
        await cls.download_thumbnail(thumbnail_url=audio_details.thumbnail_url, save_path=thumbnail_file_path)

        # Wait for the audio download to complete
        await audio_download_task

        # Rename the audio file to include the title
        os.rename(audio_file_path, new_audio_file_path)

        # Create AudioData instance with the downloaded audio and metadata
        audio_data = AudioData(file_path=new_audio_file_path,
                               thumbnail_path=thumbnail_file_path,
                               **audio_details.model_dump())

        # Process the audio file to add metadata and cover art
        await cls.process_audio(audio_data=audio_data)

        return audio_data

    @classmethod
    @final
    def _get_audio_file_path(cls, filename: str = None) -> str:

        if not filename:
            filename = valid_filename(str(uuid.uuid4().hex))

        download_dir = os.getcwd() + "/tmp"
        file_path = f"{download_dir}/{filename}.mp3"

        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        return file_path

    @classmethod
    @final
    def _get_thumbnail_file_path(cls) -> str:
        filename = valid_filename(str(uuid.uuid4().hex))
        download_dir = os.getcwd() + "/tmp"
        file_path = f"{download_dir}/{filename}_thumbnail.jpg"

        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        return file_path

    @classmethod
    @abstractmethod
    async def get_audio_details(cls, url: str) -> AudioMetadata:
        """
        Download details from the given URL.

        :param url: The URL of the audio.
        :return: AudioData containing metadata and thumbnail URL.
        """
        pass

    @classmethod
    @abstractmethod
    async def download_audio(cls, url: str, save_path: str) -> None:
        """
        Download the audio file from the given URL and save it to the specified path.

        :param url: The URL of the audio.
        :param save_path: The path where the audio file will be saved.
        :return: AudioData containing the audio file and metadata.
        """
        pass

    @classmethod
    @final
    async def download_thumbnail(cls, thumbnail_url: str, save_path: str) -> None:
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
        thumbnail_path = audio_data.thumbnail_path

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

    @staticmethod
    def _write_file(file_path: str, content: bytes) -> None:
        """Helper method to write file content."""
        with open(file_path, 'wb') as f:
            f.write(content)
