import os
import re
import logging
from datetime import datetime

import requests
import urllib3
from dotenv import load_dotenv

load_dotenv()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Suppress only the InsecureRequestWarning (the remote site needs -k)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]

# ── Constants ────────────────────────────────────────────────────────────────
HEADERS = {
    "Host": "questure.poliziadistato.it",
    "Sec-Ch-Ua": '"Not(A:Brand";v="8", "Chromium";v="144"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Encoding": "gzip, deflate, br",
    "Priority": "u=0, i",
}

COOKIES = {
    "cookieconsent_status": "dismiss",
}

BASE_URL = "https://questure.poliziadistato.it/stranieri/"


# ── Permit status checker ───────────────────────────────────────────────────
def check_permit_status(permit_code: str) -> dict:
    """
    Query the Polizia di Stato portal and return a structured result.
    Returns dict with keys: status, title, description, emoji
    """
    params = {
        "lang": "italian",
        "mime": "",
        "pratica": permit_code,
        "invia": "Invia",
    }
    referer = (
        f"https://questure.poliziadistato.it/stranieri/"
        f"?lang=italian&mime=&pratica={permit_code}&invia=Invia"
    )
    headers = {**HEADERS, "Referer": referer}

    try:
        resp = requests.get(
            BASE_URL,
            params=params,
            headers=headers,
            cookies=COOKIES,
            verify=False,
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.text.lower()
    except requests.RequestException as exc:
        logger.error("Request failed for %s: %s", permit_code, exc)
        return {
            "status": "error",
            "title": "Connection Error",
            "description": (
                "Could not reach the Polizia di Stato server.\n"
                "Please try again in a few minutes."
            ),
            "emoji": "\u26a0\ufe0f",
        }

    if "la consegna" in body:
        return {
            "status": "ready",
            "title": "Ready for Pickup!",
            "description": (
                "Your permit is <b>ready</b>!\n"
                "You can now book an appointment to pick it up\n"
                "at your local Questura office."
            ),
            "emoji": "\u2705",
        }
    elif "in trattazione" in body:
        return {
            "status": "processing",
            "title": "Being Processed",
            "description": (
                "Your application is currently <b>being processed</b>.\n"
                "The Questura has started working on your permit.\n"
                "Please check back later for updates."
            ),
            "emoji": "\u23f3",
        }
    else:
        return {
            "status": "unknown",
            "title": "Not Yet Started",
            "description": (
                "No information is available for this permit code.\n"
                "Processing has <b>not started yet</b>, or the code\n"
                "may be incorrect. Double-check and try again."
            ),
            "emoji": "\u274c",
        }


# ── Helpers ──────────────────────────────────────────────────────────────────
STATUS_COLORS = {
    "ready": "\U0001f7e2",       # green circle
    "processing": "\U0001f7e1",  # yellow circle
    "unknown": "\U0001f534",     # red circle
    "error": "\u26a0\ufe0f",     # warning
}


def build_result_message(permit_code: str, result: dict) -> str:
    dot = STATUS_COLORS.get(result["status"], "\u2753")
    return (
        f"{'=' * 28}\n"
        f"{result['emoji']}  <b>{result['title']}</b>\n"
        f"{'=' * 28}\n\n"
        f"\U0001f4c4  <b>Permit Code:</b>  <code>{permit_code}</code>\n"
        f"{dot}  <b>Status:</b>  {result['title']}\n\n"
        f"{result['description']}\n\n"
        f"{'─' * 28}"
    )


def normalize_permit_code(raw: str) -> str:
    """
    Normalize user input into a full permit code.
    - 10 alphanumeric chars  → use as-is          (e.g. 26BO123456)
    - 6 digits only          → prepend current year (e.g. 123456 → 26123456)
    - anything else           → uppercase & return as-is, let the API decide
    """
    code = raw.strip().upper()
    # If exactly 6 digits, prepend current 2-digit year
    if re.match(r"^\d{6}$", code):
        year_prefix = str(datetime.now().year % 100).zfill(2)
        code = year_prefix + code
    return code


def is_permit_code(text: str) -> bool:
    """Return True if the text looks like a permit code (6–20 alphanumeric chars)."""
    return bool(re.match(r"^[A-Za-z0-9]{6,20}$", text.strip()))


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("\U0001f50d  Check Permit Status", callback_data="check")],
            [InlineKeyboardButton("\u2139\ufe0f  Help", callback_data="help")],
        ]
    )


# ── Handlers ─────────────────────────────────────────────────────────────────
async def start(update: Update, context) -> None:
    """Send welcome message with main menu."""
    welcome = (
        "\U0001f1ee\U0001f1f9  <b>Permesso di Soggiorno Tracker</b>\n"
        f"{'━' * 30}\n\n"
        "Welcome! I can check the status of your\n"
        "<b>Italian residence permit</b> (Permesso di Soggiorno)\n"
        "directly from the Polizia di Stato portal.\n\n"
        "\U0001f4cc <b>How it works:</b>\n"
        "  Just send me your permit code anytime!\n"
        "  (e.g. <code>26BO123456</code> or just <code>123456</code>)\n\n"
        "\U0001f4a1 <i>Tip: If you send only 6 digits, the current\n"
        f"year (<code>{str(datetime.now().year % 100).zfill(2)}</code>) "
        "is added automatically.</i>\n\n"
        f"{'─' * 30}\n"
        "\U0001f447  <i>Choose an option or just type your code</i>"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            welcome, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            welcome, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard()
        )


async def check_button(update: Update, context) -> None:
    """User tapped 'Check Permit Status'."""
    query = update.callback_query
    await query.answer()

    year = str(datetime.now().year % 100).zfill(2)
    prompt = (
        "\U0001f4dd  <b>Enter Your Permit Code</b>\n"
        f"{'─' * 28}\n\n"
        "Please type or paste your permit code.\n\n"
        "\U0001f4cb  <b>Accepted formats:</b>\n"
        f"  \u2022  Full code:  <code>{year}BO123456</code>  (10 chars)\n"
        f"  \u2022  Short code: <code>123456</code>  (6 digits)\n\n"
        "\U0001f4a1 <i>If you send 6 digits, the current year\n"
        f"prefix (<code>{year}</code>) is added automatically.</i>"
    )
    await query.edit_message_text(prompt, parse_mode=ParseMode.HTML)


async def handle_message(update: Update, context) -> None:
    """
    Handle ANY text message.  If it looks like a permit code, check it.
    Otherwise, nudge the user.
    """
    text = update.message.text.strip()

    if not is_permit_code(text):
        await update.message.reply_text(
            "\U0001f914  That doesn't look like a permit code.\n\n"
            "Send a <b>6-digit</b> or <b>10-character</b> alphanumeric code,\n"
            "or tap /start to see the menu.",
            parse_mode=ParseMode.HTML,
        )
        return

    permit_code = normalize_permit_code(text)

    # Send a "checking…" message
    checking_msg = await update.message.reply_text(
        "\u23f3  <i>Checking your permit status, please wait…</i>",
        parse_mode=ParseMode.HTML,
    )

    result = check_permit_status(permit_code)
    reply = build_result_message(permit_code, result)

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("\U0001f504  Check Another", callback_data="check")],
            [InlineKeyboardButton("\U0001f3e0  Main Menu", callback_data="home")],
        ]
    )

    await checking_msg.edit_text(reply, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def help_button(update: Update, context) -> None:
    """Show help information (inline button)."""
    query = update.callback_query
    await query.answer()

    help_text = (
        "\u2139\ufe0f  <b>Help & Information</b>\n"
        f"{'━' * 28}\n\n"
        "\U0001f4d6  <b>What is this bot?</b>\n"
        "This bot checks the status of your Italian\n"
        "residence permit (Permesso di Soggiorno) by\n"
        "querying the official Polizia di Stato portal.\n\n"
        "\U0001f4cb  <b>Accepted Formats:</b>\n"
        "  \u2022  <code>26BO123456</code>  — full 10-char code\n"
        "  \u2022  <code>123456</code>  — 6 digits (year auto-added)\n\n"
        "\U0001f6a6  <b>Status Meanings:</b>\n\n"
        "\U0001f7e2  <b>Ready for Pickup</b>\n"
        "  Your permit is ready! Book an appointment\n"
        "  at your Questura to collect it.\n\n"
        "\U0001f7e1  <b>Being Processed</b>\n"
        "  Your application is in progress.\n"
        "  Check back periodically.\n\n"
        "\U0001f534  <b>Not Yet Started</b>\n"
        "  No info found. Processing hasn't begun\n"
        "  or the code might be wrong.\n\n"
        f"{'─' * 28}\n"
        "\U0001f4ac  <b>Commands:</b>\n"
        "  /start  — Main menu\n"
        "  /check  — Prompt for a permit code\n"
        "  /help   — This help message\n\n"
        f"{'─' * 28}\n"
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\U0001f3e0  Main Menu", callback_data="home")]]
    )
    await query.edit_message_text(help_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def help_command(update: Update, context) -> None:
    """Handle /help command."""
    help_text = (
        "\u2139\ufe0f  <b>Help & Information</b>\n"
        f"{'━' * 28}\n\n"
        "\U0001f6a6  <b>Status Meanings:</b>\n\n"
        "\U0001f7e2  <b>Ready for Pickup</b> — Book an appointment!\n"
        "\U0001f7e1  <b>Being Processed</b> — Check back later.\n"
        "\U0001f534  <b>Not Yet Started</b> — Processing hasn't begun.\n\n"
        "\U0001f4cb  <b>Formats:</b>  <code>26BO123456</code> or <code>123456</code>\n\n"
        "\U0001f4ac  <b>Commands:</b>  /start  /check  /help"
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\U0001f50d  Check Now", callback_data="check")]]
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def check_command(update: Update, context) -> None:
    """Handle /check command — just show the prompt, user sends code as next message."""
    year = str(datetime.now().year % 100).zfill(2)
    prompt = (
        "\U0001f4dd  <b>Enter Your Permit Code</b>\n"
        f"{'─' * 28}\n\n"
        "Please type or paste your permit code.\n\n"
        "\U0001f4cb  <b>Accepted formats:</b>\n"
        f"  \u2022  Full code:  <code>{year}BO123456</code>  (10 chars)\n"
        f"  \u2022  Short code: <code>123456</code>  (6 digits)\n"
    )
    await update.message.reply_text(prompt, parse_mode=ParseMode.HTML)


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("help", help_command))

    # Inline-keyboard callbacks
    app.add_handler(CallbackQueryHandler(check_button, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(help_button, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^home$"))

    # Any text message → auto-detect permit codes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting …")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
