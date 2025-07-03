from models.models import User
from services.auth import AuthService


async def get_or_create_user(user_id: int, first_name: str, username: str = None, last_name: str = None):
    """
    Get or create a user in the database.
    """

    user_data = (await AuthService.check_authentication(user_id)
                 or await AuthService.register_user(user_id, first_name, username, last_name))
    return User(data=user_data)