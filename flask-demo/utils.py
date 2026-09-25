"""Shared helpers used across services."""
import csv
import re

from extensions import supabase


def read_csv_file(file_path):
    rows = []

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:
            reader = csv.DictReader(file)
            rows = list(reader)

    except FileNotFoundError:
        print(f"Không tìm thấy file: {file_path}")

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
    """
    Đọc toàn bộ dữ liệu Supabase theo từng trang.
    Giống cách skills/items đang dùng.
    """
    rows = []
    start = 0

    while True:
        query = supabase.table(table_name).select("*")

        if order_column:
            try:
                query = query.order(order_column)
            except Exception:
                pass

        try:
            response = (
                query
                .range(start, start + page_size - 1)
                .execute()
            )
        except Exception as exc:
            # Thử không order
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
