"""Настройки бота. Секреты задаются через переменные окружения в .env.max."""
import os
from dotenv import load_dotenv

load_dotenv(".env.max")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
