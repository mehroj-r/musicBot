import asyncio
import contextlib
import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from musicbot.handlers.admin import IsAdmin
from musicbot.services.yandex import DeviceCode, SignInStatus, YandexAuth, YandexError

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

# Sign-ins waiting for their code to be entered, kept so they aren't garbage collected
pending_sign_ins: set[asyncio.Task] = set()


class YandexCallback(CallbackData, prefix="yandex"):
    action: str  # "sign_in" or "sign_out"


def render_status(status: SignInStatus | None) -> tuple[str, InlineKeyboardMarkup | None]:
    lines = ["🎵 <b>Yandex Music</b>", ""]
    keyboard = InlineKeyboardBuilder()

    if status is None:
        lines.append(
            "Not signed in, so Yandex Music links can't be downloaded. "
            "Sign in with an account that has Yandex Plus."
        )
        keyboard.button(text="🔑 Sign in", callback_data=YandexCallback(action="sign_in"))
        return "\n".join(lines), keyboard.as_markup()

    if status.account:
        lines.append(f"Signed in as <b>{html.escape(status.account.login)}</b>")
        if status.account.has_plus:
            lines.append("Yandex Plus: ✅")
        else:
            lines.append("Yandex Plus: ❌ (only 30-second previews can be downloaded)")
    else:
        lines.append(f"⚠️ {html.escape(status.error or 'The sign-in could not be checked')}")

    if status.from_env:
        lines += ["", "The token comes from <code>YANDEX_MUSIC_TOKEN</code>; change it there."]
        return "\n".join(lines), None

    if status.expires_at:
        lines.append(f"Renewed automatically; valid until {status.expires_at:%Y-%m-%d}.")
    keyboard.button(text="🔑 Sign in again", callback_data=YandexCallback(action="sign_in"))
    keyboard.button(text="🚪 Sign out", callback_data=YandexCallback(action="sign_out"))
    return "\n".join(lines), keyboard.as_markup()


@router.message(Command("yandex"))
async def yandex_command(message: Message, yandex: YandexAuth) -> None:
    text, markup = render_status(await yandex.status())
    await message.answer(text, reply_markup=markup)


async def finish_sign_in(message: Message, yandex: YandexAuth, code: DeviceCode) -> None:
    """
    Wait for the code to be entered, then replace it with the outcome.
    """
    try:
        account = await yandex.wait_for_sign_in(code)
    except YandexError as e:
        text = (
            f"❌ Couldn't sign in to Yandex Music: {html.escape(str(e))}.\n\n"
            "Use /yandex to try again."
        )
    except Exception:
        logger.exception("Signing in to Yandex Music failed")
        text = "❌ Something went wrong while signing in. Use /yandex to try again."
    else:
        text = f"✅ Signed in to Yandex Music as <b>{html.escape(account.login)}</b>."
        if not account.has_plus:
            text += (
                "\n\n⚠️ This account has no Yandex Plus, so only 30-second previews can be "
                "downloaded. Use /yandex to sign in with one that has it."
            )
    with contextlib.suppress(TelegramAPIError):
        await message.edit_text(text)


@router.callback_query(YandexCallback.filter(F.action == "sign_in"))
async def sign_in(callback: CallbackQuery, yandex: YandexAuth, bot: Bot) -> None:
    try:
        code = await yandex.request_code()
    except YandexError as e:
        await callback.answer(f"{e}. Please try again.", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🌐 Enter the code", url=code.verification_url)
    message = await bot.send_message(
        callback.from_user.id,
        "🔑 <b>Sign in to Yandex Music</b>\n\n"
        f"Open {code.verification_url} and enter this code:\n\n"
        f"<code>{html.escape(code.user_code)}</code>\n\n"
        f"Use the account that has Yandex Plus. The code works for {code.expires_in // 60} "
        "minutes; this message changes once you're signed in.",
        reply_markup=keyboard.as_markup(),
    )
    await callback.answer()

    task = asyncio.create_task(finish_sign_in(message, yandex, code))
    pending_sign_ins.add(task)
    task.add_done_callback(pending_sign_ins.discard)


@router.callback_query(YandexCallback.filter(F.action == "sign_out"))
async def sign_out(callback: CallbackQuery, yandex: YandexAuth) -> None:
    await yandex.sign_out()
    text, markup = render_status(None)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer("Signed out of Yandex Music")
