"""App configuration and path constants."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"  # CSV backup (export từ Supabase)
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "Mashkyrielight@!#1234567890",
)

USERS_FILE = BASE_DIR / "users.csv"
RACES_CSV = DATA_DIR / "races.csv"
TITLES_CSV = DATA_DIR / "titles.csv"
# fallback root nếu chưa chuyển vào data/
if not RACES_CSV.exists():
    RACES_CSV = BASE_DIR / "races.csv"
if not TITLES_CSV.exists():
    TITLES_CSV = BASE_DIR / "titles.csv"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY", "").strip()
    or os.environ.get("SUPABASE_ANON_KEY", "").strip()
)
