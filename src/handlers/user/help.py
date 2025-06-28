from aiogram import types, Router, F

router = Router()

@router.message(F.text.startswith("/help"))
async def help_handler(message: types.Message) -> None | types.Message:

    return await message.reply(
        "Here are the commands you can use:\n"
        "/start - Start the bot\n"
        "/help - Get help information",
    )