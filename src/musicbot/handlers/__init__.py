from aiogram import F, Router

from musicbot.handlers import download, fallback, start


def setup_routers() -> Router:
    router = Router()
    # Only talk in private chats; stay silent if someone adds the bot to a group
    router.message.filter(F.chat.type == "private")
    # The fallback must come last: it answers anything the others didn't handle
    router.include_routers(start.router, download.router, fallback.router)
    return router
