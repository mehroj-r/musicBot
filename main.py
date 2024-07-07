import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, FSInputFile
from aiogram.filters import Command
from func import download_audio
from client import uploadBigFile
from credentials import BOT_API_TOKEN, channel_id

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=BOT_API_TOKEN)
dp = Dispatcher()

# Set bot commands
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Start the bot"),
        BotCommand(command="/help", description="Get help information")
    ]
    await bot.set_my_commands(commands)

async def send_photo(chat_id, photo_path, caption):
    photo = FSInputFile(photo_path)
    await bot.send_photo(chat_id, photo, caption=caption, parse_mode=ParseMode.MARKDOWN)

# Handler for the /start command
@dp.message(Command('start'))
async def send_welcome(message: types.Message):
    await message.reply("""**🎵 Welcome to YouTube Audio Downloader Bot! 🎵**
    
Hello! I’m your friendly YouTube Audio Downloader Bot. My job is to help you effortlessly save music from YouTube as audio files. Here’s how I can assist you:

1. Send me a YouTube video link.
2. I’ll convert it to an audio file.
3. The audio file will be sent directly to your private channel.

No more manual downloads or conversions. Enjoy your favorite music in just a few taps!

Happy listening! 🎧""", parse_mode=ParseMode.MARKDOWN)

# Handler for the /help command
@dp.message(Command('help'))
async def send_help(message: types.Message):
    await message.reply("Here are the commands you can use:\n/start - Start the bot\n/help - Get help information", parse_mode=ParseMode.MARKDOWN)

# Handler for text messages
@dp.message(F.text)
async def echo_message(message: types.Message):
    if message.text.startswith("https://www.youtube.com/watch?") or message.text.startswith("https://youtu.be/"):
        downloading_sent = await message.reply("Downloading ...", disable_web_page_preview=True)
        file_location, thumbnail_location, file_caption, data = download_audio(message.text)

        await bot.edit_message_text(
            text=f"**🎵 {data['title']}**\n\nDownloading - DONE\nUploading ...",
            chat_id=message.chat.id,
            message_id=downloading_sent.message_id,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

        if os.path.getsize(file_location) > 52428800:
            await uploadBigFile(file_location, thumbnail_location, data)

        else:
            await upload_to_telegram(file_location, thumbnail_location, file_caption,  message.chat.id)

        await send_photo(message.chat.id, thumbnail_location, f"**🎵 {data['title']}**\n\nSuccessfully uploaded to the channel.")
        await bot.delete_message(chat_id=message.chat.id, message_id=downloading_sent.message_id)
        await bot.delete_message(chat_id=message.chat.id, message_id=downloading_sent.message_id - 1)
        os.remove(file_location)
        os.remove(thumbnail_location)
    else:
        await message.reply("Invalid URL")


# Function to upload a file to Telegram
async def upload_to_telegram(file_path, thumbnail_path, file_caption, chat_id):
    if not os.path.isfile(file_path):
        logging.error("The specified file does not exist.")
        return
    try:
        audio_file = FSInputFile(file_path)
        thumbnail_file = FSInputFile(thumbnail_path)
        await bot.send_audio(chat_id=channel_id, audio=audio_file, caption=f"🔉 **{file_caption}**", thumbnail=thumbnail_file, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"An error occurred while uploading the file: {e}")

# Main function to start the bot
async def main():
    await set_commands(bot)
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
