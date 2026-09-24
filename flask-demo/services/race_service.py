"""Races data access (CSV + rewards/fans)."""
import re

from flask import url_for

from config import BASE_DIR
from services.item_service import load_items_by_id
from utils import read_csv_file


def load_races():
    return read_csv_file("races.csv")


def build_race_slug_by_name():
    """Tạo bảng tra cứu slug theo tên race, dùng cho linkify_race_names()."""
    races_by_name = {}

    for race in load_races():
        name = race.get("name", "").strip()
        slug = race.get("slug", "").strip()

        if name and slug:
            races_by_name[name] = slug

    return races_by_name


def linkify_race_names(text):
    """
    Tự động biến tên race xuất hiện trong 1 đoạn text (vd cột
    'Conditions' của Secret Events) thành link tới trang race đó.

    Vì dữ liệu race của bạn gộp chung Classic/Senior thành 1 race, nên
    hậu tố " (Classic)" / " (Senior)" đứng ngay sau tên race trong text
    vẫn được giữ nguyên hiển thị trong link, nhưng chỉ dùng phần tên
    race (không tính hậu tố) để tra slug.
    """
    if not text:
        return text

    races_by_name = build_race_slug_by_name()

    if not races_by_name:
        return text

    # Khớp tên dài trước, để "Tokyo Yushun (Japanese Derby)" (chính
    # tên race, không phải hậu tố) được match trọn vẹn thay vì dừng
    # sớm ở "Tokyo Yushun".
    sorted_names = sorted(races_by_name.keys(), key=len, reverse=True)

    pattern = (
        "(" + "|".join(re.escape(name) for name in sorted_names) + ")"
        r"(\s*\((?:Classic|Senior|Junior)\))?"
    )

    def replace(match):
        race_name = match.group(1)
        suffix = match.group(2) or ""
        slug = races_by_name.get(race_name, "")

        if not slug:
            return match.group(0)

        url = url_for("race_detail", slug=slug)

        return (
            f'<a class="tevent-race-link" href="{url}">'
            f'{race_name}{suffix}</a>'
        )

    return re.sub(pattern, replace, text)


def load_race_rewards(race_slug):
    reward_rows = read_csv_file("race_rewards.csv")
    items_by_id = load_items_by_id()

    rewards = []

    for reward in reward_rows:
        if reward.get("race_slug", "").strip() != race_slug:
            continue

        item_id = reward.get("item_id", "").strip()
        item = items_by_id.get(item_id, {})

        rewards.append({
            "item_id": item_id,
            "item_name": item.get("name", item_id),
            "item_image": item.get("image", "default_item.png"),
            "quantity": reward.get("quantity", ""),
            "drop_rate": reward.get("drop_rate", ""),
            "sort_order": reward.get("sort_order", "")
        })

    return rewards


def load_race_fans(race_slug):
    fan_rows = read_csv_file("race_fans.csv")

    return [
        row
        for row in fan_rows
        if row.get("race_slug", "").strip() == race_slug
    ]


def get_races_by_slugs(slugs):
    """
    Đọc nhiều Race cùng lúc theo slug, dùng cho mục Objectives ở trang
    character detail. Hiện tại race vẫn đang lưu ở races.csv (local),
    chưa đưa lên Supabase, nên đọc thẳng từ đó qua load_races().
    """
    normalized_slugs = {
        slug.strip()
        for slug in slugs
        if slug and slug.strip()
    }

    if not normalized_slugs:
        return {}

    return {
        race["slug"]: race
        for race in load_races()
        if race.get("slug", "") in normalized_slugs
    }