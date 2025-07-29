from config import settings
from services.mongo import MongoService

_client = MongoService(
    uri=settings.MONGO_URI,
    db_name=settings.MONGO_DB
)

db = _client.db

async def init_db():
    """
    Initialize the database connection.
    """
    await _client.init_db()