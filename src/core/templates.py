from pydantic import BaseModel, Field

class AudioMetadata(BaseModel):
    artist: str = Field(..., description="Artist of the audio")
    title: str = Field(..., description="Title of the audio")
    thumbnail_url: str = Field(..., description="URL of the thumbnail image")

class AudioData(BaseModel):
    file_path: str = Field(default=None, description="Path to the audio file")
    thumbnail_path: str = Field(default=None, description="Path to save the thumbnail image")

    artist: str = Field(..., description="Artist of the audio")
    title: str = Field(..., description="Title of the audio")
    thumbnail_url: str = Field(..., description="URL of the thumbnail image")