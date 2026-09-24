"""App configuration and path constants."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "Mashkyrielight@!#1234567890",
)

USERS_FILE = BASE_DIR / "users.csv"
RACES_CSV = BASE_DIR / "races.csv"
TITLES_CSV = BASE_DIR / "titles.csv"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY", "").strip()
    or os.environ.get("SUPABASE_ANON_KEY", "").strip()
)
