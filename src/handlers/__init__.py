from .user import setup_user_handlers
from .main import setup_main_handlers

def register_all_handlers(dp):
    setup_user_handlers(dp)
    setup_main_handlers(dp)