"""Scenarios list — đọc Supabase (fallback CSV nếu lỗi)."""
from collections import defaultdict

from utils import (
    fetch_all_supabase_rows,
    normalize_supabase_row,
    read_csv_file,
)


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _s(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _truthy(value):
    if value is True or value is False:
        return bool(value)
    return _s(value).lower() in ("1", "true", "yes", "y", "t")


def _load_table(table_name, csv_name, order_column=None):
    """Ưu tiên Supabase; lỗi / rỗng thì fallback CSV local."""
    try:
        raw = fetch_all_supabase_rows(table_name, order_column=order_column)
        rows = [normalize_supabase_row(r) for r in (raw or [])]
        if rows:
            return rows
    except Exception as exc:
        print(f"[scenarios] Supabase {table_name} lỗi: {exc} — fallback CSV")
    return read_csv_file(csv_name)


# Soft caps hiển thị trên GameTora "after future rebalance" (Global)
SOFT_CAPS_OVERRIDE = {
    "ura-finals": {
        "cap_speed": "1400",
        "cap_stamina": "1400",
        "cap_power": "1400",
        "cap_guts": "1400",
        "cap_wit": "1400",
    },
    "unity-cup": {
        "cap_speed": "1300",
        "cap_stamina": "1300",
        "cap_power": "1300",
        "cap_guts": "1300",
        "cap_wit": "1800",
    },
    "trackblazer": {
        "cap_speed": "1200",
        "cap_stamina": "1900",
        "cap_power": "1200",
        "cap_guts": "1200",
        "cap_wit": "1500",
    },
    "our-grand-concert": {
        "cap_speed": "1600",
        "cap_stamina": "1300",
        "cap_power": "1300",
        "cap_guts": "1500",
        "cap_wit": "1300",
    },
    "grand-masters": {
        "cap_speed": "1500",
        "cap_stamina": "1400",
        "cap_power": "1500",
        "cap_guts": "1300",
        "cap_wit": "1300",
    },
}


def load_linked_characters_by_scenario():
    grouped = defaultdict(list)
    for row in _load_table(
        "scenario_linked_characters",
        "scenario_linked_characters.csv",
        order_column="sort_order",
    ):
        sid = _s(row.get("scenario_id"))
        if not sid:
            continue
        image = _s(row.get("image"))
        image_dir = _s(row.get("image_dir")) or "scenario_chars"
        grouped[sid].append({
            "char_id": _s(row.get("char_id")),
            "name": _s(row.get("name")),
            "url_name": _s(row.get("url_name")),
            "image": image,
            "image_dir": image_dir,
            "sort_order": _int(row.get("sort_order"), 0),
        })
    for items in grouped.values():
        items.sort(key=lambda x: x["sort_order"])
    return grouped


def load_scenarios():
    linked = load_linked_characters_by_scenario()
    scenarios = []

    for row in _load_table("scenarios", "scenarios.csv", order_column="order"):
        sid = _s(row.get("id"))
        if not sid:
            continue

        slug = _s(row.get("slug"))
        caps = {
            "cap_speed": _s(row.get("cap_speed")),
            "cap_stamina": _s(row.get("cap_stamina")),
            "cap_power": _s(row.get("cap_power")),
            "cap_guts": _s(row.get("cap_guts")),
            "cap_wit": _s(row.get("cap_wit")),
        }
        if slug in SOFT_CAPS_OVERRIDE:
            caps.update(SOFT_CAPS_OVERRIDE[slug])

        scenarios.append({
            "id": sid,
            "slug": slug,
            "name": _s(row.get("name")),
            "name_full": _s(row.get("name_full")) or _s(row.get("name")),
            "name_ja": _s(row.get("name_ja")),
            "order": _int(row.get("order"), 0),
            "bg_color": (_s(row.get("bg_color")) or "cccccc").lstrip("#"),
            "release_date": _s(row.get("release_date")),
            "secret_events": _s(row.get("secret_events")) or "Available",
            **caps,
            "image": _s(row.get("image")),
            "is_current": _truthy(row.get("is_current")),
            "cap_note": "after future rebalance" if slug == "grand-masters" else "",
            "linked_characters": linked.get(sid, []),
        })

    scenarios.sort(key=lambda s: s["order"])
    return scenarios


def get_current_scenarios():
    return [s for s in load_scenarios() if s.get("is_current")]


def get_upcoming_scenarios():
    return [s for s in load_scenarios() if not s.get("is_current")]
