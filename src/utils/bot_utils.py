from aiogram.types import BotCommand


async def set_descripton(bot, description: str):
    """
    Set the bot's description.
    """
    try:
        await bot.set_my_description(description, language_code="en")
    except Exception as e:
        raise Exception(f"Failed to set bot description: {e}")

async def set_commands(bot, commands: list[BotCommand]):
    """
    Set the bot's commands.
    """
    try:
        await bot.set_my_commands(commands)
    except Exception as e:
        raise Exception(f"Failed to set bot commands: {e}")

async def set_short_description(bot, short_description: str):
    """
    Set the bot's short description.
    """
    try:
        await bot.set_my_short_description(short_description, language_code="en")
    except Exception as e:
        raise Exception(f"Failed to set bot small description: {e}")