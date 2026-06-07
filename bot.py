import asyncio
import ipaddress
import logging
import os
from io import StringIO
from typing import Optional

import paramiko
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WAITING_FOR_IP = 1
ADD_IP_BUTTON_TEXT = "Добавить IP адрес"


class ConfigError(Exception):
    pass


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ConfigError(f"Environment variable {name} is required")
    return value.strip()


def build_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton(ADD_IP_BUTTON_TEXT)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_ids() -> set[int]:
    raw_value = get_required_env("ADMINS_IDS")
    parts = [part.strip() for part in raw_value.split(",") if part.strip()]
    if not parts:
        raise ConfigError("ADMINS_IDS must contain at least one Telegram ID")

    admin_ids: set[int] = set()
    for part in parts:
        try:
            admin_ids.add(int(part))
        except ValueError as exc:
            raise ConfigError(
                f"ADMINS_IDS contains non-integer value: {part}"
            ) from exc

    return admin_ids


def parse_private_key(private_key_raw: str) -> paramiko.PKey:
    key_text = private_key_raw.replace("\\n", "\n")
    key_file = StringIO(key_text)

    key_parsers = [
        paramiko.Ed25519Key.from_private_key,
        paramiko.RSAKey.from_private_key,
        paramiko.ECDSAKey.from_private_key,
        paramiko.DSSKey.from_private_key,
    ]

    last_exception: Optional[Exception] = None
    for parser in key_parsers:
        key_file.seek(0)
        try:
            return parser(key_file)
        except Exception as exc:  # pragma: no cover
            last_exception = exc

    raise ConfigError(
        "Failed to parse BOT_TARGET_SSH_PRIVATE_KEY"
    ) from last_exception


def run_remote_iptables_commands(allowed_ip: str) -> None:
    ssh_host = get_required_env("BOT_TARGET_SSH_HOST")
    ssh_username = get_required_env("BOT_TARGET_SSH_USERNAME")

    ssh_port_raw = os.getenv("BOT_TARGET_SSH_PORT", "22").strip()
    try:
        ssh_port = int(ssh_port_raw)
    except ValueError as exc:
        raise ConfigError("BOT_TARGET_SSH_PORT must be an integer") from exc

    private_key_value = get_required_env("BOT_TARGET_SSH_PRIVATE_KEY")
    private_key = parse_private_key(private_key_value)

    commands = [
        "iptables -D DOCKER-USER -p tcp --dport 25565 -j DROP",
        (
            "iptables -A DOCKER-USER -p tcp --dport 25565 "
            f"-s {allowed_ip} -j ACCEPT"
        ),
        "iptables -A DOCKER-USER -p tcp --dport 25565 -j DROP",
    ]

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=ssh_host,
            port=ssh_port,
            username=ssh_username,
            pkey=private_key,
            timeout=15,
        )

        for command in commands:
            stdin, stdout, stderr = client.exec_command(command)
            stdin.close()
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                error_output = (
                    stderr.read()
                    .decode("utf-8", errors="replace")
                    .strip()
                )
                raise RuntimeError(
                    "Command failed "
                    f"(exit {exit_code}): {command}. "
                    f"{error_output}"
                )
    finally:
        client.close()


async def ensure_admin(update: Update) -> bool:
    if update.effective_user is None or update.message is None:
        return False

    try:
        admin_ids = get_admin_ids()
    except ConfigError:
        await update.message.reply_text(
            "Некорректный ADMINS_IDS в переменных окружения."
        )
        return False

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("Доступ запрещен.")
        return False

    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    del context
    if not await ensure_admin(update):
        return ConversationHandler.END

    assert update.message is not None
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=build_keyboard(),
    )
    return ConversationHandler.END


async def prompt_ip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    del context
    if not await ensure_admin(update):
        return ConversationHandler.END

    assert update.message is not None
    await update.message.reply_text("Введите IP адрес для разрешения доступа:")
    return WAITING_FOR_IP


async def add_ip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    del context
    if not await ensure_admin(update):
        return ConversationHandler.END

    assert update.message is not None
    ip_text = (update.message.text or "").strip()

    try:
        parsed_ip = ipaddress.ip_address(ip_text)
    except ValueError:
        await update.message.reply_text(
            "IP адрес некорректный. Попробуйте снова:"
        )
        return WAITING_FOR_IP

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            run_remote_iptables_commands,
            str(parsed_ip),
        )
    except Exception as exc:
        logger.exception("Failed to update iptables")
        await update.message.reply_text(
            f"Не удалось применить правила iptables: {exc}"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"IP адрес {parsed_ip} успешно добавлен.",
        reply_markup=build_keyboard(),
    )
    return ConversationHandler.END


async def fallback_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    del context
    if not await ensure_admin(update):
        return ConversationHandler.END

    assert update.message is not None
    await update.message.reply_text(
        "Используйте кнопку ниже:",
        reply_markup=build_keyboard(),
    )
    return ConversationHandler.END


def main() -> None:
    token = get_required_env("TELEGRAM_BOT_TOKEN")

    application = Application.builder().token(token).build()

    conversation_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f"^{ADD_IP_BUTTON_TEXT}$"),
                prompt_ip,
            ),
        ],
        states={
            WAITING_FOR_IP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_ip),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_menu),
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conversation_handler)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_menu)
    )

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
