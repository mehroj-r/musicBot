from core.models import PyObjectId, TimestampedModel, SoftDeleteModel

from pydantic import Field

class User(TimestampedModel, SoftDeleteModel):
    db_collection = 'users'

    id: PyObjectId | None = Field(default=None, alias="_id", exclude=True)
    user_id: int = Field(frozen=True)
    first_name: str
    is_active: bool = Field(default=True)
    username: str | None
    last_name: str | None


class Channel(TimestampedModel, SoftDeleteModel):
    db_collection = 'channels'

    id: PyObjectId | None = Field(default=None, alias="_id", exclude=True)
    channel_id: int = Field(frozen=True)
    user_id: PyObjectId | None
    title: str
    description: str | None