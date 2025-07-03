from dotenv import load_dotenv
import os

# Load environment variables from a .env file
load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_API_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
CHANNEL_URL = os.getenv("CHANNEL_URL")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# MongoDB
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

# Miscellaneous
COOKIES_FILE = os.getenv("COOKIE_FILE")