"""Trainer titles — ưu tiên data/titles.csv, sau đó Supabase."""
from utils import fetch_all_supabase_rows, normalize_supabase_row, read_csv_file


def load_titles():
    # 1) Local backup trong data/
    rows = read_csv_file("titles.csv")
    titles = []
    for row in rows:
        titles.append({
            "id": (row.get("id") or "").strip(),
            "name": (row.get("name") or "").strip(),
            "requirement": (row.get("requirement") or "").strip(),
            "image": (row.get("image") or "").strip(),
            "sort_order": (row.get("sort_order") or "").strip(),
        })

    # 2) Supabase nếu CSV trống
    if not titles:
        print("[titles] CSV trống — thử Supabase")
        for raw in fetch_all_supabase_rows("titles", order_column="sort_order"):
            row = normalize_supabase_row(raw)
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
