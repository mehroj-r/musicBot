from yt_dlp.utils import DownloadError, sanitize_filename


def safe_filename(name: str, max_bytes: int = 200) -> str:
    """
    Make a filesystem-safe file name (without extension) from an arbitrary title.
    Truncates by bytes so multibyte titles stay under the 255-byte name limit.
    """
    cleaned = sanitize_filename(name).strip()
    truncated = cleaned.encode()[:max_bytes].decode(errors="ignore").strip()
    return truncated or "audio"


def describe_download_error(error: Exception) -> str:
    """
    Turn a yt-dlp failure into a message that can be shown to the user.
    """
    if not isinstance(error, DownloadError):
        return "Something went wrong while downloading."

    message = str(error).lower()
    known_errors = [
        ("private video", "This video is private."),
        ("confirm your age", "This video is age-restricted."),
        ("not a bot", "YouTube is blocking the server right now. Please try again later."),
        ("not available in your country", "This video is not available in the server's region."),
        ("live event", "Live streams can't be downloaded."),
        ("is live", "Live streams can't be downloaded."),
        ("unsupported url", "This link is not supported."),
        ("looks truncated", "This link looks incomplete. Please copy it again."),
        ("unavailable", "This video is unavailable."),
    ]
    for needle, reply in known_errors:
        if needle in message:
            return reply
    return "Could not download this video."
