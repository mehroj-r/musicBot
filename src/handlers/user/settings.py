from aiogram import types, Router, F

router = Router()

@router.message(F.text.startswith("/settings"))
async def settings_handler(message: types.Message):

    return await message.answer(
        "Coming soon! This feature is under development."
    )