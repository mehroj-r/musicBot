#!/usr/bin/env bash
# Refresh the YouTube cookies the bot uses once YouTube starts asking the server to
# "confirm you're not a bot".
#
# Opens a dedicated Chromium/Chrome profile, waits for you to sign in and close it,
# exports the cookies with yt-dlp and, after you confirm, installs them on the server.
# The profile and the server settings are kept for next time.
set -euo pipefail
# Everything this script writes (settings, profile, cookies) is readable by you only
umask 077

usage() {
    cat <<'EOF'
Usage: scripts/refresh-youtube-cookies.sh [options]

Opens the dedicated YouTube browser profile, exports its cookies once you close the
window, and uploads them to the bot's server after you confirm.

Options:
  --reconfigure   Ask for the server, bot folder, browser and profile again
  --upload-only   Skip the browser and upload the cookies exported last time
  -h, --help      Show this help

Settings: ~/.config/musicbot/youtube-cookies.conf
Cookies:  ~/.local/share/musicbot/youtube-cookies.txt (kept after every export)
EOF
}

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/musicbot/youtube-cookies.conf"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/musicbot"
COOKIES="$DATA_DIR/youtube-cookies.txt"
# Any public video: yt-dlp needs one request to export the cookies
TEST_URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
# The bot's user inside the container (see the Dockerfile)
CONTAINER_UID=1000

die() {
    echo "Error: $*" >&2
    exit 1
}

# ask VARIABLE "Question" default: prompt, keeping the default on an empty answer
ask() {
    local reply=""
    read -r -p "$2 [$3]: " reply || true
    printf -v "$1" '%s' "${reply:-$3}"
}

configure() {
    local default_browser
    default_browser=$(basename "$(command -v chromium || command -v google-chrome-stable ||
        command -v google-chrome || echo chromium)")

    ask SERVER "SSH host of the server running the bot" "${SERVER:-}"
    [[ -n $SERVER ]] || die "the server is required"
    ask REMOTE_DIR "Bot folder on that server" "${REMOTE_DIR:-/root/musicBot}"
    ask BROWSER "Browser to open (chromium or google-chrome)" "${BROWSER:-$default_browser}"
    ask PROFILE_DIR "Folder for the dedicated YouTube profile" "${PROFILE_DIR:-$DATA_DIR/youtube-profile}"

    mkdir -p "$(dirname "$CONFIG_FILE")"
    printf 'SERVER=%q\nREMOTE_DIR=%q\nBROWSER=%q\nPROFILE_DIR=%q\n' \
        "$SERVER" "$REMOTE_DIR" "$BROWSER" "$PROFILE_DIR" >"$CONFIG_FILE"
    echo "Saved to $CONFIG_FILE"
}

# yt-dlp's name for the browser, which decides how the cookie database is read
ytdlp_browser() {
    case $(basename "$BROWSER") in
        chromium*) echo chromium ;;
        google-chrome* | chrome) echo chrome ;;
        brave*) echo brave ;;
        *) die "unsupported browser '$BROWSER'; use chromium or google-chrome (--reconfigure)" ;;
    esac
}

ytdlp() {
    if command -v uv >/dev/null; then
        uv run --quiet --project "$REPO_DIR" yt-dlp "$@"
    elif command -v yt-dlp >/dev/null; then
        yt-dlp "$@"
    else
        die "needs uv (to use the project's yt-dlp) or yt-dlp on PATH"
    fi
}

open_browser() {
    command -v "$BROWSER" >/dev/null || die "$BROWSER is not installed (--reconfigure to pick another)"
    # A second launch would hand over to the running window and return straight away
    if pgrep -f -- "--user-data-dir=$PROFILE_DIR" >/dev/null; then
        die "the YouTube profile is already open; close that window and run this again"
    fi
    mkdir -p "$PROFILE_DIR"

    cat <<EOF

A $BROWSER window opens with the dedicated YouTube profile. In it:
  1. Sign in to YouTube if you aren't already (a secondary Google account is safest)
  2. Play any video for a few seconds
  3. Go to https://www.youtube.com/robots.txt, leaving it as the only tab
  4. Close the window. Don't sign out: that would invalidate the cookies

EOF
    read -r -p "Press Enter to open the browser..." || true
    # Plain-text cookie storage, so yt-dlp can read them without the system keyring
    "$BROWSER" --user-data-dir="$PROFILE_DIR" --password-store=basic --no-first-run \
        --no-default-browser-check --new-window "https://www.youtube.com/" >/dev/null 2>&1 || true
    echo "Browser closed."
}

export_cookies() {
    local browser tmp_dir exported login_cookies
    browser=$(ytdlp_browser)
    mkdir -p "$DATA_DIR"
    # yt-dlp first reads the --cookies file if it exists, and rejects an empty one,
    # so export to a new path in a private temporary folder
    tmp_dir=$(mktemp -d "$DATA_DIR/export.XXXXXX")
    trap 'rm -rf "$tmp_dir"' EXIT
    exported="$tmp_dir/cookies.txt"

    echo "Exporting cookies..."
    ytdlp --cookies-from-browser "$browser+basictext:$PROFILE_DIR/Default" --cookies "$exported" \
        --skip-download --no-warnings --print "Checked with: %(title)s" "$TEST_URL" ||
        die "yt-dlp could not export the cookies"

    login_cookies=$(grep -cE $'\t(LOGIN_INFO|__Secure-3PSID)\t' "$exported" || true)
    if ((login_cookies == 0)); then
        die "the profile isn't signed in to YouTube; sign in before closing the window"
    fi
    mv "$exported" "$COOKIES"
}

summarize() {
    local count expiry
    # Netscape format: domain, subdomains, path, secure, expiry, name, value
    read -r count expiry < <(awk -F'\t' 'NF >= 7 {
        n++
        if ($6 ~ /^(LOGIN_INFO|__Secure-3PSID)$/ && $5 > 0 && (min == "" || $5 < min)) min = $5
    } END { print n + 0, min + 0 }' "$COOKIES")

    echo "$count cookies in $COOKIES"
    if ((expiry > 0)); then
        echo "The login lasts until $(date -d "@$expiry" '+%Y-%m-%d') at most; YouTube can end it sooner."
    fi
}

upload() {
    local answer remote_tmp
    # No answer (e.g. no terminal) counts as no
    read -r -p "Upload them to $SERVER:$REMOTE_DIR and enable them for the bot? [y/N] " answer ||
        answer=""
    if [[ $answer != [yY]* ]]; then
        echo "Not uploaded. The cookies stay in $COOKIES (upload later with --upload-only)."
        return
    fi

    remote_tmp="/tmp/musicbot-cookies.$RANDOM$RANDOM"
    scp -q "$COOKIES" "$SERVER:$remote_tmp"
    ssh "$SERVER" bash -s -- "$REMOTE_DIR" "$remote_tmp" "$CONTAINER_UID" <<'REMOTE'
set -euo pipefail
dir=$1 tmp=$2 uid=$3
trap 'rm -f "$tmp"' EXIT
cd "$dir"
[[ -f .env ]] || { echo "Error: no .env in $dir" >&2; exit 1; }

mkdir -p secrets
was_missing=$([[ -f secrets/cookies.txt ]] && echo no || echo yes)
# Only the bot's container user may read the file; without root, fall back to world-readable
if ! install -o "$uid" -g "$uid" -m 600 "$tmp" secrets/cookies.txt 2>/dev/null &&
    ! sudo -n install -o "$uid" -g "$uid" -m 600 "$tmp" secrets/cookies.txt 2>/dev/null; then
    install -m 644 "$tmp" secrets/cookies.txt
    echo "Warning: no root here, so the cookies file is readable by every user on the server."
fi
echo "Installed $dir/secrets/cookies.txt"

# Point the bot at the file, replacing older or commented-out settings
wanted=COOKIES_FILE=/app/secrets/cookies.txt
env_changed=no
if ! grep -qx "$wanted" .env; then
    sed -i -E '/^#?[[:space:]]*COOKIES?_FILE=/d' .env
    echo "$wanted" >>.env
    env_changed=yes
    echo "Enabled $wanted in .env"
fi

# The bot copies the file for every download, so it only needs a restart when it
# started without cookies
if [[ $env_changed == yes || $was_missing == yes ]]; then
    echo "Restarting the bot..."
    docker compose up -d --force-recreate music-bot
else
    echo "No restart needed: the next download uses the new cookies."
fi
if docker compose exec -T music-bot test -r /app/secrets/cookies.txt; then
    echo "The bot can read the new cookies."
else
    echo "Warning: the bot can't read /app/secrets/cookies.txt; check the file's owner." >&2
    exit 1
fi
REMOTE
}

reconfigure=false
upload_only=false
while (($#)); do
    case $1 in
        --reconfigure) reconfigure=true ;;
        --upload-only) upload_only=true ;;
        -h | --help) usage && exit 0 ;;
        *) usage >&2 && exit 2 ;;
    esac
    shift
done

SERVER="" REMOTE_DIR="" BROWSER="" PROFILE_DIR=""
# shellcheck source=/dev/null
[[ -f $CONFIG_FILE ]] && source "$CONFIG_FILE"
if $reconfigure || [[ -z $SERVER ]]; then
    configure
fi

if $upload_only; then
    [[ -f $COOKIES ]] || die "nothing exported yet; run without --upload-only first"
else
    ytdlp_browser >/dev/null # refuse an unsupported browser before you sign in
    open_browser
    export_cookies
fi
summarize
upload
