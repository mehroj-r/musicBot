# Music Bot (Telegram)

A professional Telegram bot that downloads audio from YouTube videos and uploads them to a private Telegram channel. Built with modern Python async frameworks and robust error handling.

---
## Features
- Download audio from YouTube videos using `yt-dlp`.
- Upload audio files to a private Telegram channel (up to 4GB, Telegram limit).
- Adds metadata and cover art to audio files.
- Asynchronous, scalable, and modular codebase.
- Detailed logging for monitoring and debugging.

---
## Requirements
- Python 3.12+
- [ffmpeg](https://ffmpeg.org/) installed and available in your system PATH
- A Telegram account (for channel uploads >50MB)
- A Telegram Bot token ([@BotFather](https://t.me/BotFather))
- API ID and API Hash from [my.telegram.org](https://my.telegram.org)

---
## Installation
1. **Clone the repository:**
   ```bash
git clone https://github.com/mehroj-r/musicBot.git
cd musicBot
```
2. **Install dependencies:**
   ```bash
uv sync
```
   Or, if you use [Poetry](https://python-poetry.org/):
   ```bash
poetry install
```

---
## Configuration
1. **Create a `.env` file in the project root with the following content:**
   ```env
BOT_API_TOKEN=<your-telegram-bot-token>
API_ID=<your-api-id>
API_HASH=<your-api-hash>
PHONE_NUMBER=<your-phone-number>
CHANNEL_URL=<your-channel-url>
CHANNEL_ID=<your-channel-id>
```
   - You can obtain the Bot token from [@BotFather](https://t.me/BotFather).
   - API ID and API Hash are available at [my.telegram.org](https://my.telegram.org).
   - `CHANNEL_URL` is the invite or public link to your channel.
   - `CHANNEL_ID` is the numeric ID (e.g., `-1001234567890`).

2. **Ensure `ffmpeg` is installed and accessible from your system PATH.**

---
## Usage
Run the bot from the project root:
```bash
uv run src/core/main.py
```



---
## Logging
- Logs are written to `app.log` (info/debug) and `errors.log` (errors) in the project root.
- Console output is also enabled for real-time monitoring.

---
## Project Structure
```
src/
  config/           # Configuration and logging setup
  core/             # Main bot logic and entry point
  handlers/         # Command and message handlers
  services/         # YouTube download and Telegram upload services
  utils/            # Utility functions
```

---
## Contributing
Pull requests and issues are welcome! Please open an issue to discuss your ideas or report bugs.