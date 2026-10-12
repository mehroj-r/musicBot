import re

from aiogram.types import Message

URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def extract_url(message: Message) -> str | None:
    """
    Return the first link in a message: a hidden text link, a detected URL, or a raw match.
    """
    text = message.text or message.caption or ""
    for entity in message.entities or message.caption_entities or []:
        if entity.type == "text_link" and entity.url:
            return entity.url
        if entity.type == "url":
            url = entity.extract_from(text)
            # Telegram also detects scheme-less links like "youtu.be/..."
            return url if "://" in url else f"https://{url}"

    match = URL_PATTERN.search(text)
    return match.group(0) if match else None


async def has_link(message: Message) -> dict[str, str] | bool:
    """
    aiogram filter: passes the link to the handler as ``url``.
    """
    url = extract_url(message)
    return {"url": url} if url else False
