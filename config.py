import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str  # postgresql://user:pass@host:port/dbname

def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not bot_token:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")
    if not database_url:
        raise RuntimeError("Не задан DATABASE_URL в переменных окружения.")

    return Config(bot_token=bot_token, database_url=database_url)
