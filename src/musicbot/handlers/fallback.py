from aiogram import Router
from aiogram.types import Message

router = Router()


@router.message()
async def fallback_handler(message: Message) -> None:
    await message.reply("Send me a link to a track or video, and I'll turn it into audio.")
