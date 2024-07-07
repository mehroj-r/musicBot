import random
from telethon import TelegramClient
from telethon.tl.types import InputFile, InputFileBig, DocumentAttributeAudio
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import InputMediaUploadedDocument
from telethon.utils import get_input_peer
from credentials import api_id, api_hash, phone_number, channel_url

# Initiate Telegram Client
client = TelegramClient('session_name', api_id, api_hash)

async def main(file_path: str, cover_image_path: str, data: dict[str, str]):
    await client.start(phone=phone_number)

    # Get the entity of the destination (username, chat id, etc.)
    entity = await client.get_entity(channel_url)
    input_peer = get_input_peer(entity)

    # Upload the file cover image
    cover_image = await client.upload_file(cover_image_path)

    # Upload the file with increased chunk size
    file = await client.upload_file(file_path)

    # Check if the file is large and handle accordingly
    if isinstance(file, InputFileBig):
        input_file = InputFileBig(
            id=file.id,
            parts=file.parts,
            name=file.name
        )
    else:
        input_file = InputFile(
            id=file.id,
            parts=file.parts,
            name=file.name,
            md5_checksum=file.md5_checksum
        )

    # Check if the cover image is large and handle accordingly
    if isinstance(cover_image, InputFileBig):
        input_cover_image = InputFileBig(
            id=cover_image.id,
            parts=cover_image.parts,
            name=cover_image.name
        )
    else:
        input_cover_image = InputFile(
            id=cover_image.id,
            parts=cover_image.parts,
            name=cover_image.name,
            md5_checksum=cover_image.md5_checksum
        )

    # Set audio attributes
    audio_attributes = DocumentAttributeAudio(
        duration=0,  # Replace with actual duration if known
        voice=False,  # Set to True if the file is a voice message
        title=data['title'],  # Replace with the actual title
        performer=data['artist']  # Replace with the actual performer

    )

    # Create the media document
    media = InputMediaUploadedDocument(
        file=input_file,
        mime_type='audio/mpeg',  # Set the appropriate MIME type for audio files
        attributes=[audio_attributes],
        thumb=input_cover_image
    )

    # Send the media document
    result = await client(SendMediaRequest(
        peer=input_peer,
        media=media,
        message=data['title'],
        random_id=random.randint(-9223372036854775808, 9223372036854775807)
    ))


async def uploadBigFile(file_path: str, cover_image_path: str, data: dict[str, str]):
    await main(file_path, cover_image_path, data)