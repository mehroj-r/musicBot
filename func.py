import requests
import pydub
from yt_dlp import YoutubeDL
import os

illegal_chars = ["\\", "/", ":", "*", "?", "\"", "<", ">", "|"]

def valid_filename(filename: str) -> str:
    valid = ""
    for i in filename:
        if i in illegal_chars:
            valid += "_"
        else:
            valid += i
    return valid.strip(".")

def download_audio(url: str) -> tuple[str, str, str, dict[str, str]]:
    # Extract video info without downloading
    with YoutubeDL() as ydl:
        info_dict = ydl.extract_info(url, download=False)
        audio_title = info_dict['title']
        uploader = info_dict['uploader']
        valid_title = valid_filename(audio_title)

        # Customize filename
        custom_filename = valid_title

        # Avoid Filename Limit Error
        if len(custom_filename) > 250:
            custom_filename = custom_filename[:250]

        # Update yt-dlp options with custom filename
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{custom_filename}.%(ext)s',
            'keepvideo': True,  # Keep the original video file,
            'quiet': True,
            'noprogreess':True,
        }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    cur_dir = os.getcwd()
    file_path = f"{cur_dir}/{custom_filename}.mp3"
    thumbnail_path = f"{cur_dir}/{custom_filename}_cover.jpg"
    audio_thumbnail = info_dict['thumbnail']
    data = {"artist": uploader, "title": audio_title}

    # Download the thumbnail file
    r = requests.get(audio_thumbnail, allow_redirects=True)
    open(thumbnail_path, 'wb').write(r.content)

    # The original audio file downloaded by yt-dlp (usually in .webm format)
    downloaded_audio = f"{custom_filename}.webm"

    # Convert the audio file to mp3 and add metadata
    pydub.AudioSegment.from_file(downloaded_audio).export(
        file_path,
        bitrate="128k",
        tags={"artist": uploader, "title": audio_title},
        format='mp3',
        cover=thumbnail_path,
        id3v2_version='3'
    )

    # Remove the original downloaded file after conversion
    os.remove(downloaded_audio)

    return file_path, thumbnail_path, audio_title, data
