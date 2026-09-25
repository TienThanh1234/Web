"""Trainer titles (Supabase + CSV fallback)."""
from utils import fetch_all_supabase_rows, normalize_supabase_row, read_csv_file


def load_titles():
    """Đọc Titles từ Supabase; fallback titles.csv nếu rỗng."""
    raw_rows = fetch_all_supabase_rows("titles", order_column="sort_order")

    titles = []
    for raw_row in raw_rows:
        row = normalize_supabase_row(raw_row)
        titles.append({
            "id": (row.get("id") or "").strip(),
            "name": (row.get("name") or "").strip(),
            "requirement": (row.get("requirement") or "").strip(),
            "image": (row.get("image") or "").strip(),
            "sort_order": (row.get("sort_order") or "").strip(),
        })

    if not titles:
        print("[titles] Supabase 0 dòng — fallback titles.csv")
        for row in read_csv_file("titles.csv"):
            titles.append({
                "id": (row.get("id") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "requirement": (row.get("requirement") or "").strip(),
                "image": (row.get("image") or "").strip(),
                "sort_order": (row.get("sort_order") or "").strip(),
            })

    def sort_key(item):
        try:
            return int(item.get("sort_order") or 0)
        except ValueError:
            return 0

    titles.sort(key=sort_key)
    return titles
