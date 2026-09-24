"""Trainer titles (CSV)."""
from config import BASE_DIR, TITLES_CSV
from utils import read_csv_file


def load_titles():
    rows = read_csv_file(TITLES_CSV)

    titles = []
    for row in rows:
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
