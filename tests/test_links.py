import datetime

from aiogram.types import Chat, Message, MessageEntity

from musicbot.services.links import extract_url


def message(text: str, entities: list[MessageEntity] | None = None) -> Message:
    return Message(
        message_id=1,
        date=datetime.datetime.now(datetime.UTC),
        chat=Chat(id=1, type="private"),
        text=text,
        entities=entities,
    )


def test_plain_url_in_text():
    assert extract_url(message("listen https://youtu.be/abc please")) == "https://youtu.be/abc"


def test_hidden_text_link():
    entity = MessageEntity(type="text_link", offset=0, length=4, url="https://youtu.be/xyz")
    assert extract_url(message("this", [entity])) == "https://youtu.be/xyz"


def test_scheme_less_link_detected_by_telegram():
    text = "youtu.be/abc"
    entity = MessageEntity(type="url", offset=0, length=len(text))
    assert extract_url(message(text, [entity])) == "https://youtu.be/abc"


def test_entity_offsets_count_utf16_units():
    # The emoji takes two UTF-16 code units, which Telegram offsets are measured in
    text = "🎵 https://youtu.be/abc"
    entity = MessageEntity(type="url", offset=3, length=20)
    assert extract_url(message(text, [entity])) == "https://youtu.be/abc"


def test_no_link():
    assert extract_url(message("hello there")) is None
