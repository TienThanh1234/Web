"""Shared helpers used across services."""
import csv
import re
from pathlib import Path

from config import BASE_DIR, DATA_DIR
from extensions import supabase


def resolve_csv_path(file_path):
    """
    Tìm file CSV theo thứ tự:
      1. Đường dẫn tuyệt đối / path có sẵn
      2. data/<tên file>   (backup export từ Supabase)
      3. <root>/<tên file>
    """
    path = Path(file_path)

    if path.is_absolute() and path.exists():
        return path

    name = path.name

    candidates = [
        path,                      # relative as given
        DATA_DIR / name,           # data/characters.csv
        BASE_DIR / name,           # root characters.csv
        BASE_DIR / "data" / name,  # phòng DATA_DIR lệch
    ]

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue

    return DATA_DIR / name  # default message path


def read_csv_file(file_path):
    rows = []
    resolved = resolve_csv_path(file_path)

    try:
        with open(
            resolved,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            reader = csv.DictReader(file)
            rows = list(reader)

    except FileNotFoundError:
        print(f"Không tìm thấy file: {file_path} (đã thử data/ và root)")

    return rows


def make_short_description(text):
    if text is None:
        return ""

    text = re.sub(r"\s*\[[^\]]*\]", "", text)

    return text.strip()


def text_to_id(text):
    """Đổi tên skill/event thành dạng id dùng được trong URL."""
    if text is None:
        return ""

    text = text.strip().lower()
    text = text.replace("◎", "oo")
    text = text.replace("○", "o")
    text = re.sub(r"[^a-z0-9]+", "_", text)

    return text.strip("_")


def normalize_supabase_row(row):
    """Chuẩn hóa một dòng Supabase thành các chuỗi giống csv.DictReader."""
    return {
        str(key): "" if value is None else str(value).strip()
        for key, value in dict(row or {}).items()
    }


def fetch_all_supabase_rows(
    table_name,
    order_column="id",
    page_size=1000,
):
    """Đọc toàn bộ dữ liệu Supabase theo từng trang."""
    rows = []
    start = 0

    while True:
        query = supabase.table(table_name).select("*")

        if order_column:
            query = query.order(order_column)

        try:
            response = (
                query
                .range(start, start + page_size - 1)
                .execute()
            )
        except Exception as exc:
            print(f"[Supabase] {table_name} lỗi: {exc}")
            try:
                response = (
                    supabase
                    .table(table_name)
                    .select("*")
                    .range(start, start + page_size - 1)
                    .execute()
                )
            except Exception as exc2:
                print(f"[Supabase] {table_name} thất bại: {exc2}")
                break

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    return rows
