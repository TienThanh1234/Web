"""Shared clients (Supabase)."""
from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL

if not SUPABASE_URL:
    raise RuntimeError(
        "Thiếu SUPABASE_URL trong file .env hoặc biến môi trường."
    )

if not SUPABASE_KEY:
    raise RuntimeError(
        "Thiếu SUPABASE_KEY hoặc SUPABASE_ANON_KEY "
        "trong file .env hoặc biến môi trường."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
