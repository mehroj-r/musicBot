# Music Bot (Telegram)

Telegram Bot that downloads audio from YouTube video and uploads to the private channel

---
## Features
- Download audio from YouTube videos.
- Upload audio to a private Telegram channel.
- Supports file size up-to 2GB (Telegram Limit)
---
## Requirements
- Python 3.6+
- Everything inside 'requirements.txt'
- 'ffmpeg' installed in system variables (OS dependent)
- A Telegram Account for a workaround of 50MB upload limit for Bots
---
## Installation
1. Clone the repository:

```
git clone https://github.com/mehroj-r/musicBot.git
cd musicBot
```
2. Install required libraries:
s
```
pip install -r requirements.txt
```
---
## Configuration
Update 'credentials.py' with correct values

```python
# Get from @BotFather
BOT_API_TOKEN = "<Telegram Bot API Token>" 

# Get from my.telegram.org
api_id = 19284623
api_hash = "19t9iulb4e20240e951f789056f87520"
phone_number = "+1xxxxxxxxx"

# Update channel details
channel_url = "telegram.me/joinchat/eHyr7JKQWA2Hji9"
channel_id = -1001234567890
```

### Usage
Run the bot
```bash
python main.py
```