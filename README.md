# Music Bot (Telegram)

A Telegram bot that turns links from YouTube, YouTube Music, SoundCloud, Bandcamp and
[other sites supported by yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
into tagged audio files and posts them to a Telegram channel.

## Features
- Downloads audio with `yt-dlp`, including YouTube's JavaScript challenges (via Deno).
- Writes title, artist and square cover art into the file; sends a proper Telegram thumbnail.
- Uploads up to 50 MB through the Bot API, or up to 2000 MB with Telethon or a local Bot API
  server (see [Large files](#large-files)).
- Refuses playlists, live streams and tracks above a configurable length; limits parallel downloads.
- Stores users in SQLite (SQLAlchemy + Alembic); migrations run automatically on startup.

## Running with Docker
Requirements: Docker with the Compose plugin.

1. Create the configuration:
   ```bash
   cp .env.example .env
   ```
   Set at least `BOT_API_TOKEN` (from [@BotFather](https://t.me/BotFather)) and `CHANNEL_ID`
   (numeric, e.g. `-1001234567890`). Add the bot to the channel as an admin that can post.
2. Optional: YouTube cookies help with age-restricted videos and bot checks. Export them in
   Netscape format and save them as `secrets/cookies.txt` (mounted read-only into the container).
3. Start the bot:
   ```bash
   docker compose up -d --build
   ```

Data (the SQLite database and the Telethon session) lives in the `bot-data` volume. Logs go to
stdout: `docker compose logs -f music-bot`.

## Configuration
All settings come from environment variables (or `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `BOT_API_TOKEN` | required | Bot token from @BotFather |
| `CHANNEL_ID` | required | Channel the audio is posted to |
| `API_ID`, `API_HASH` | unset | App credentials from [my.telegram.org](https://my.telegram.org), for large files |
| `LOCAL_BOT_API_URL` | unset | URL of a local Bot API server, for large files |
| `COOKIES_FILE` | unset | Netscape-format cookies for yt-dlp |
| `MAX_PARALLEL_DOWNLOADS` | `2` | Downloads running at once; more requests wait in line |
| `MAX_DURATION_MINUTES` | `180` | Longest track the bot will download |
| `DATA_DIR` | `data` | Where the database and Telethon session are stored |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Large files
The cloud Bot API refuses uploads above 50 MB (about 36 minutes of MP3). The bot picks an
upload mode from the configuration and logs it on startup:

- **Neither set:** files above 50 MB are refused with a message.
- **`API_ID` and `API_HASH` set:** files above 50 MB are uploaded with Telethon, logged in
  **as the bot** (no phone number or personal account involved).
- **`LOCAL_BOT_API_URL` set:** every upload goes through a self-hosted Bot API server, up to 2000 MB.
  It takes precedence over Telethon. To switch to it:
  1. Log the bot out of the cloud Bot API once (afterwards it can't log back in there for 10 minutes):
     ```bash
     curl "https://api.telegram.org/bot$BOT_API_TOKEN/logOut"
     ```
  2. Add to `.env` (with `API_ID` and `API_HASH` also set):
     ```env
     COMPOSE_PROFILES=local-bot-api
     LOCAL_BOT_API_URL=http://telegram-bot-api:8081
     ```
  3. `docker compose up -d` starts the `telegram-bot-api` service next to the bot.

## Development
Requirements: [uv](https://docs.astral.sh/uv/), ffmpeg, and [Deno](https://deno.com/) for YouTube.

```bash
uv sync                    # install dependencies
uv run musicbot            # run the bot (reads .env)
uv run pytest              # tests
uv run ruff check .        # lint
uv run ruff format .       # format
```

Outside Docker, point `COOKIES_FILE` at a local path such as `secrets/cookies.txt`.

After changing the models in `src/musicbot/db/models.py`, generate a migration and review it:
```bash
uv run alembic revision --autogenerate -m "describe the change"
```

## Deployment
- **CI** (`.github/workflows/ci.yml`) lints, tests and builds the image for every pull request
  and every push to `master`.
- **Deploy** (`.github/workflows/deploy.yml`) runs after CI passes on `master`: it pulls on the
  server over SSH, builds the new image, then restarts the containers.
- **yt-dlp updates** (`.github/workflows/update-yt-dlp.yml`) run daily. When a new yt-dlp is out,
  the workflow commits the updated `uv.lock` to `master`, which goes through CI and the deploy.

## Project Structure
```
src/musicbot/
  __main__.py      # entry point: settings, logging, migrations, then the bot
  app.py           # bot, dispatcher and upload-mode wiring
  config.py        # settings from the environment
  db/              # SQLAlchemy models, database setup, Alembic migrations
  handlers/        # /start, /help, link downloads, fallback
  middlewares.py   # registers users
  services/        # yt-dlp downloads, artwork and tags, uploads
tests/             # pytest suite
```
