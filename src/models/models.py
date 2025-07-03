from dataclasses import dataclass
from typing import Any


@dataclass
class BaseDataClass:
    """Base data class for all data classes"""

    @staticmethod
    def _is_supported_nested_type(value: Any) -> bool:
        """
        Check if the value is a supported nested type for conversion to dict.

        :param value: The value to check.
        """
        return hasattr(value, 'to_dict') and callable(value.to_dict)

    def to_dict(self, exclude_keys: set = None, include_extra: dict = None, skip_none: bool = True) -> dict:
        """
        Convert the data class to a dictionary.
        It can also handle nested objects, lists, and dictionaries.

        :param exclude_keys: Set of keys to exclude from the dictionary.
        :param include_extra: Dictionary of extra key-value pairs to include.
        :param skip_none: If True, skip keys with None values.
        """

        result = {}

        for k, v in self.__dict__.items():

            # Skip None values if skip_none is True
            if v is None and skip_none:
                continue

            # Skip excluded keys
            if k in (exclude_keys or set()):
                continue

            # Handle nested objects
            if self._is_supported_nested_type(v):
                result[k] = v.to_dict()
            # Handle lists/tuples with potential nested objects
            elif isinstance(v, (list, tuple)):
                result[k] = [
                    item.to_dict() if self._is_supported_nested_type(item) else item
                    for item in v
                ]
            # Handle dictionaries with potential nested objects
            elif isinstance(v, dict):
                result[k] = {
                    dict_k: dict_v.to_dict() if self._is_supported_nested_type(dict_v) else dict_v
                    for dict_k, dict_v in v.items()
                }
            else:
                result[k] = v

            # Include only specified keys
            result[k] = v

        for k, v in (include_extra or {}).items():
            result[k] = v

        return result

@dataclass
class User(BaseDataClass):
    """Data class representing a user in the system."""
    user_id: int
    first_name: str
    is_active: bool
    username: str = None
    last_name: str = None

    def __init__(self, data):
        """
        Initialize the User data class with the provided data.

        :param data: Dictionary containing user data.
        """
        self.user_id = getattr(data, 'user_id', None)
        self.first_name = getattr(data, 'first_name', None)
        self.is_active = getattr(data, 'is_active', True)
        self.username = getattr(data, 'username', None)
        self.last_name = getattr(data, 'last_name', None)