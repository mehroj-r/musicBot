from .start import router as start_router
from .help import router as help_router
from .settings import router as settings_router

def setup_user_handlers(dp):
    dp.include_router(start_router)
    dp.include_router(help_router)
    dp.include_router(settings_router)