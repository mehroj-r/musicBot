# Music Bot (Telegram)

A private Telegram bot that turns links from YouTube, YouTube Music, SoundCloud, Bandcamp and
[other sites supported by yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
into tagged audio files, sent back in the chat or posted to the user's channel.

## Features
- Private: admins grant access by user ID; strangers' requests reach the admins with an Allow button.
- Per-user `/settings`: M4A (default, no re-encoding) or MP3, and an optional channel to post to.
- Downloads audio with `yt-dlp`, including YouTube's JavaScript challenges (via Deno), and
  shows the progress while it works.
- Sends tracks that were already uploaded again instantly, without downloading them, from a
  cache of Telegram file IDs (per track and format).
- Writes title, artist and square cover art into the file; sends a proper Telegram thumbnail.
- Uploads up to 50 MB through the Bot API, or up to 2000 MB with Telethon or a local Bot API
  server (see [Large files](#large-files)).
- Refuses playlists, live streams and tracks above a configurable length; limits parallel downloads.
- Stores users, settings and the track cache in SQLite (SQLAlchemy + Alembic); migrations run
  on startup.

## Running with Docker
Requirements: Docker with the Compose plugin.

1. Create the configuration:
   ```bash
   cp .env.example .env
   ```
   Set `BOT_API_TOKEN` (from [@BotFather](https://t.me/BotFather)) and `ADMIN_IDS`, your
   numeric Telegram user ID. If you don't know it, start the bot without it and send it a
   message: it replies with your ID.
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
| `ADMIN_IDS` | empty | Comma-separated user IDs of admins; with none, nobody can use the bot |
| `API_ID`, `API_HASH` | unset | App credentials from [my.telegram.org](https://my.telegram.org), for large files |
| `LOCAL_BOT_API_URL` | unset | URL of a local Bot API server, for large files |
| `COOKIES_FILE` | unset | Netscape-format cookies for yt-dlp |
| `MAX_PARALLEL_DOWNLOADS` | `2` | Downloads running at once; more requests wait in line |
| `MAX_DURATION_MINUTES` | `180` | Longest track the bot will download |
| `DATA_DIR` | `data` | Where the database and Telethon session are stored |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Using the bot
- **Access:** when someone without access messages the bot, they get their user ID and every
  admin gets a request with **Allow** / **Ignore** buttons (at most once a day per person).
  Admins can also use `/allow USER_ID`, `/revoke USER_ID` and `/users`.
- **Format:** `/settings` switches between M4A (YouTube's original AAC, no re-encoding) and MP3.
- **Destination:** audio comes back in the chat. To post it to a channel instead, tap
  **Post to a channel** in `/settings` and pick one you manage; Telegram adds the bot there as
  an admin that can post.

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
  access.py        # access requests and admin notifications
  handlers/        # /start, /help, admin commands, /settings, link downloads, fallback
  middlewares.py   # registers users and checks their access
  services/        # yt-dlp downloads, artwork and tags, uploads
tests/             # pytest suite
```
