from pathlib import Path

from mutagen.id3 import APIC, TIT2, TPE1
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image

from musicbot.config import AudioFormat

COVER_MAX_SIZE = 800
# Telegram only accepts JPEG thumbnails up to 320x320 and 200 kB
THUMBNAIL_SIZE = 320


def make_artwork(source: Path, work_dir: Path) -> tuple[Path, Path]:
    """
    Center-crop the source image to a square cover and a Telegram thumbnail, both JPEG.
    YouTube art tracks put the album cover in the middle of a 16:9 frame.

    :return: Paths of the cover and the thumbnail.
    """
    cover_path = work_dir / "cover.jpg"
    thumbnail_path = work_dir / "thumbnail.jpg"

    with Image.open(source) as image:
        image = image.convert("RGB")
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        square = image.crop((left, top, left + side, top + side))

    cover_side = min(side, COVER_MAX_SIZE)
    square.resize((cover_side, cover_side), Image.Resampling.LANCZOS).save(
        cover_path, "JPEG", quality=90
    )
    square.resize((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS).save(
        thumbnail_path, "JPEG", quality=85
    )
    return cover_path, thumbnail_path


def write_tags(
    path: Path, audio_format: AudioFormat, title: str, artist: str, cover: Path | None
) -> None:
    """
    Write title, artist and cover art into the file without re-encoding it.
    """
    cover_data = cover.read_bytes() if cover else None

    if audio_format is AudioFormat.MP3:
        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        if cover_data:
            audio.tags.add(
                APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data)
            )
    else:
        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["\xa9nam"] = [title]
        audio.tags["\xa9ART"] = [artist]
        if cover_data:
            audio.tags["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]

    audio.save()
