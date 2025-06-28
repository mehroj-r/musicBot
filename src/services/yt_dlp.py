import os

import pydub
import requests
import yt_dlp

from config.logging_config import logger
from utils.dlp_utils import valid_filename


class DLPService:

    @classmethod
    def download_audio(cls, url: str) -> tuple[str, str, str, dict[str, str]]:

        # Use yt_dlp Python API to extract video info and download audio
        logger.info(" - Extracting audio details ...")

        # Get audio information without downloading for display purposes
        audio_info = cls._get_audio_info(url)

        audio_title = audio_info.get('title', 'audio')
        uploader = audio_info.get('uploader', 'unknown')
        audio_thumbnail = audio_info.get('thumbnail', None)
        filename = valid_filename(audio_title)[:250]

        # Prepare paths
        download_dir = os.getcwd()+"/tmp"
        file_path = f"{download_dir}/{filename}.mp3"
        thumbnail_path = f"{download_dir}/thumbnail.jpg"

        # Ensure the download directory exists
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        # Ensure the audio thmbnail URL is available
        if not audio_thumbnail:
            raise ValueError("No thumbnail URL found in audio info.")

        cls._download_thumbnail(thumbnail_url=audio_thumbnail, save_path=thumbnail_path)
        cls._download_audio_file(url=url, save_path=file_path)
        cls._process_audio_file(file_path=file_path, thumbnail_path=thumbnail_path, artist=uploader, title=audio_title)

        data = {
            "artist": uploader,
            "title": audio_title
        }

        return file_path, thumbnail_path, audio_title, data

    @classmethod
    def _get_audio_info(cls, url: str) -> dict[str, str]:
        """
        Extract audio information without downloading.
        """
        ydl_opts_info = {
            'skip_download': True,
            'quiet': True,
            'extract_flat': 'in_playlist',
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.error(f"Failed to extract audio details: {str(e)}")
            raise

        return info

    @classmethod
    def _download_thumbnail(cls, thumbnail_url: str, save_path: str) -> None:
        """
        Download the thumbnail image from the given URL.
        """
        logger.info(" - Downloading thumbnail ...")
        try:
            response = requests.get(thumbnail_url, allow_redirects=True)
            with open(save_path, 'wb') as thumb_file:
                thumb_file.write(response.content)
            logger.info(f"Thumbnail downloaded successfully to {save_path}")
        except Exception as e:
            logger.error(f"Failed to download thumbnail: {str(e)}")
            raise

    @classmethod
    def _download_audio_file(cls, url: str, save_path: str) -> None:
        logger.info(" - Downloading audio ...")
        ydl_opts_audio = {
            'format': 'bestaudio/best',
            'quiet': True,
            'outtmpl': save_path.rstrip('.mp3'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }
        with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
            ydl.download([url])

    @classmethod
    def _process_audio_file(cls, file_path: str, thumbnail_path: str, artist: str, title: str) -> None:
        """
        Process the audio file to add metadata and cover image.
        """
        logger.info(" - Processing audio ...")
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