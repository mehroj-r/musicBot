from pydantic import BaseModel, Field

class AudioMetadata(BaseModel):
    artist: str = Field(..., description="Artist of the audio")
    title: str = Field(..., description="Title of the audio")
    duration: int | None = Field(default=None, description="Duration in seconds")
    thumbnail_url: str | None = Field(default=None, description="URL of the thumbnail image")

class AudioData(AudioMetadata):
    work_dir: str = Field(..., description="Per-download directory holding all files of this job")
    file_path: str = Field(..., description="Path to the audio file")
    cover_path: str | None = Field(default=None, description="Square cover image embedded into the audio file")
    thumbnail_path: str | None = Field(default=None, description="320x320 JPEG thumbnail for Telegram")
