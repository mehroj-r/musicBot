import requests
import pydub
from pytube import YouTube
import os
from pytube.innertube import _default_clients

# Fix age restriction
_default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID_CREATOR"]

illegal_chars = ["\\", "/", ":", "*", "?", "\"", "<", ">", "|"]

def valid_filename(filename: str) -> str:
    valid = ""
    for i in filename:
        if i in illegal_chars:
            valid+="_"
        else:
            valid+=i
    return valid.strip(".")

def download_audio(url: str) -> tuple[str, str, str, dict[str, str]]:
    yt = YouTube(url)
    cur_dir = os.getcwd()
    audio_title = yt.title
    valid = valid_filename(audio_title)
    audio_thumbnail = yt.thumbnail_url
    channel_title = yt.author
    chosen_stream = yt.streams.filter(only_audio=True).first()

    file_path = f"{cur_dir}/{valid}.mp3"
    thumbnail_path = f"{cur_dir}/cover.jpg"

    data={"artist":channel_title, "title":audio_title}

    # Download the thumbnail file
    r = requests.get(audio_thumbnail, allow_redirects=True, params={"path": thumbnail_path})
    open(thumbnail_path, 'wb').write(r.content)

    # Download the audio file
    downloaded_audio = chosen_stream.download(output_path=f"{cur_dir}", filename=f"{valid}", max_retries=10)
    pydub.AudioSegment.from_file(downloaded_audio).export(file_path, bitrate="128k", tags={"artist": f"{channel_title}", "title": f"{audio_title}"}, format='mp3', cover=thumbnail_path, id3v2_version='3')
    os.remove(downloaded_audio)

    return file_path, thumbnail_path, audio_title, data