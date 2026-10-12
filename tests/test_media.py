from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from PIL import Image

from musicbot.config import AudioFormat
from musicbot.services.media import make_artwork, write_tags
from tests.conftest import make_audio_file


def test_artwork_is_square_jpeg_within_telegram_limits(tmp_path: Path):
    source = tmp_path / "cover-source.webp"
    Image.new("RGB", (1280, 720), "red").save(source, "WEBP")

    cover, thumbnail = make_artwork(source, tmp_path)

    with Image.open(cover) as image:
        assert (image.format, image.size) == ("JPEG", (720, 720))
    with Image.open(thumbnail) as image:
        assert (image.format, image.size) == ("JPEG", (320, 320))
    assert thumbnail.stat().st_size < 200 * 1024


def make_cover(tmp_path: Path) -> Path:
    cover = tmp_path / "cover.jpg"
    Image.new("RGB", (10, 10), "blue").save(cover, "JPEG")
    return cover


def test_m4a_tags(tmp_path: Path):
    path = make_audio_file(tmp_path / "audio.m4a", ["-c:a", "aac"])
    write_tags(path, AudioFormat.M4A, "Back In Black", "AC/DC", make_cover(tmp_path))

    tags = MP4(path).tags
    assert tags["\xa9nam"] == ["Back In Black"]
    assert tags["\xa9ART"] == ["AC/DC"]
    assert len(tags["covr"]) == 1


def test_mp3_tags(tmp_path: Path):
    path = make_audio_file(tmp_path / "audio.mp3", ["-c:a", "libmp3lame"])
    write_tags(path, AudioFormat.MP3, "Back In Black", "AC/DC", make_cover(tmp_path))

    tags = MP3(path).tags
    assert tags["TIT2"].text == ["Back In Black"]
    assert tags["TPE1"].text == ["AC/DC"]
    assert tags["APIC:Cover"].mime == "image/jpeg"


def test_tags_without_cover(tmp_path: Path):
    path = make_audio_file(tmp_path / "audio.m4a", ["-c:a", "aac"])
    write_tags(path, AudioFormat.M4A, "Title", "Artist", None)
    assert "covr" not in MP4(path).tags
