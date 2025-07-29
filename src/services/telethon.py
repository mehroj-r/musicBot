import asyncio
import random
from telethon import TelegramClient
from telethon.tl.types import InputFile, InputFileBig, DocumentAttributeAudio
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument
from telethon.utils import get_input_peer

from config.logging_conf import logger
from config.settings import API_ID, API_HASH, PHONE_NUMBER, CHANNEL_URL

class TelethonService:
    """
    Service for managing Telethon client operations.
    """
    client = None

    @classmethod
    async def upload_files(cls, audio_file_path: str, cover_image_path: str, data: dict[str, str]) -> None:

        # Start the Telethon client if not already started
        await cls.start_client()

        # Upload the cover image and audio file, and retrieve the input peer
        tasks = [cls.client.upload_file(cover_image_path), cls.client.upload_file(audio_file_path), cls.retrieve_input_peer()]
        cover_img, audio_file, input_peer = await asyncio.gather(*tasks)

        # Process the uploaded files to determine if they are large or small
        input_cover = cls._process_input_file(cover_img)
        input_audio = cls._process_input_file(audio_file)
        audio_attributes = cls.get_audio_attributes(data['title'], data['artist'])

        # Create the media document
        media = cls._get_media_document(
            file=input_audio,
            cover_image=input_cover,
            audio_attributes=audio_attributes
        )

        # Send the media document
        await cls.send_media(media, data['title'], input_peer)


    @classmethod
    async def start_client(cls):
        """
        Start the Telethon client.
        """
        cls.client = TelegramClient('session_name', API_ID, API_HASH)
        await cls.client.start(phone=PHONE_NUMBER)
        logger.info("Telethon client started successfully.")

    @classmethod
    async def retrieve_input_peer(cls):
        """
        Get the input peer for the channel.
        """
        entity = await cls.client.get_entity(CHANNEL_URL)
        return get_input_peer(entity)

    @classmethod
    async def send_media(cls, media, message, input_peer):
        """
        Send media to the specified input peer.
        """
        await cls.client(SendMediaRequest(
            peer=input_peer,
            media=media,
            message=message,
            random_id=random.randint(-9223372036854775808, 9223372036854775807)
        ))

    @staticmethod
    def _get_media_document(file, cover_image, audio_attributes):
        """
        Create a media document for the uploaded file.
        """
        return InputMediaUploadedDocument(
            file=file,
            mime_type='audio/mpeg',
            attributes=[audio_attributes],
            thumb=cover_image
        )


    @staticmethod
    def _process_input_file(file):
        """
        Process the uploaded file to determine if it's large or small.
        """
        if isinstance(file, InputFileBig):
            return InputFileBig(
                id=file.id,
                parts=file.parts,
                name=file.name
            )
        else:
            return InputFile(
                id=file.id,
                parts=file.parts,
                name=file.name,
                md5_checksum=file.md5_checksum
            )

    @staticmethod
    def get_audio_attributes(title: str, artist: str) -> DocumentAttributeAudio:
        """
        Create audio attributes for the uploaded file.
        """
        return DocumentAttributeAudio(
            duration=0,                         # Replace with actual duration if known
            voice=False,                        # Set to True if the file is a voice message
            title=title,                    # Replace with the actual title
            performer=artist                    # Replace with the actual performer
        )
