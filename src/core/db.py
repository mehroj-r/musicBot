from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi

from config import settings

client = AsyncMongoClient(
    settings.MONGO_URI,
    server_api=ServerApi('1')
)

async def init_db():
    """
    Initialize the database connection.
    """
    await client.admin.command('ping')

def get_db():
    """
    Get the database instance.
    """
    return getattr(client, settings.MONGO_DB)