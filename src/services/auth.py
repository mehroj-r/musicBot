from typing import Optional

from core.db import get_db
from models.models import User


class AuthService:

    @classmethod
    async def register_user(
            cls,
            user_id: int,
            first_name: str,
            username: str = None,
            last_name: str = None,
    ) -> User:
        """
        Register a new user in the database.
        """

        db = get_db()

        # Create a new user document
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "is_active": True,
        }

        # Insert the user into the database
        await db.users.insert_one(user_data)

        return await db.users.find_one({"user_id": user_id})

    @classmethod
    async def check_authentication(cls, user_id: int) -> Optional[User]:
        """
        Check if a user is authenticated.

        :param user_id: The ID of the user to check.
        """

        db = get_db()

        # Check if the user exists in the database
        user = await db.users.find_one({"user_id": user_id})

        if not user:
            return None

        return User(data=user)