"""Items data access (Supabase)."""
from extensions import supabase
from utils import fetch_all_supabase_rows, normalize_supabase_row


def load_items():
    """Đọc toàn bộ Items từ bảng public.items trên Supabase."""
    raw_rows = fetch_all_supabase_rows(
        "items",
        order_column="id"
    )

    items = []

    for raw_row in raw_rows:
        row = normalize_supabase_row(raw_row)

        if row.get("id", "") == "":
            continue

        items.append({
            "id": row.get("id", ""),
            "name": row.get("name", ""),
            "image": row.get("image", ""),
            "description": row.get("description", ""),
            "uses": row.get("uses", ""),
            "how_to_get": row.get("how_to_get", "")
        })

    return items


def get_item_by_id(item_id):
    """Đọc 1 Item từ Supabase theo id, dùng cho trang chi tiết Item."""
    normalized_item_id = (item_id or "").strip()

    if normalized_item_id == "":
        return None

    response = (
        supabase
        .table("items")
        .select("*")
        .eq("id", normalized_item_id)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    row = normalize_supabase_row(rows[0])

    return {
        "id": row.get("id", ""),
        "name": row.get("name", ""),
        "image": row.get("image", ""),
        "description": row.get("description", ""),
        "uses": row.get("uses", ""),
        "how_to_get": row.get("how_to_get", "")
    }


def load_items_by_id():
    """Tạo bảng tra cứu Item theo id từ Supabase."""
    items = load_items()

    return {
        item.get("id", "").strip(): item
        for item in items
        if item.get("id", "").strip()
    }