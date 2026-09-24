"""Support card data access (Supabase)."""
import re

from flask import current_app

from extensions import supabase
from utils import text_to_id


def _as_clean_text(value):
    """Đổi giá trị Supabase về chuỗi giống dữ liệu đọc từ CSV."""
    if value is None:
        return ""

    return str(value).strip()


def _normalize_support_card(row):
    """
    Chuẩn hóa một support card lấy từ Supabase để các template cũ
    vẫn dùng được giống khi dữ liệu còn nằm trong CSV.
    """
    card = dict(row or {})

    text_fields = [
        "id",
        "name",
        "title",
        "rarity",
        "type",
        "image",
        "thumb_image",
        "hint_skill_ids",
        "event_skill_ids",
        "highlight_skill_ids",
        "stat_gain",
        "stat_icon",
        "random_events",
    ]

    for field_name in text_fields:
        card[field_name] = _as_clean_text(card.get(field_name))

    # Nếu chưa có thumb_image thì tự dùng image như code CSV cũ.
    if card["thumb_image"] == "":
        card["thumb_image"] = card["image"]

    return card


def load_support_cards():
    """Đọc danh sách Support Card từ bảng public.support_cards."""
    response = (
        supabase
        .table("support_cards")
        .select("*")
        .order("id")
        .execute()
    )

    return [
        _normalize_support_card(row)
        for row in (response.data or [])
    ]


def get_support_card_by_id(card_id):
    """Đọc một Support Card từ Supabase theo id."""
    normalized_card_id = _as_clean_text(card_id)

    response = (
        supabase
        .table("support_cards")
        .select("*")
        .eq("id", normalized_card_id)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    return _normalize_support_card(rows[0])


def load_support_card_effects(card_id):
    """Đọc effect của một Support Card từ Supabase."""
    normalized_card_id = _as_clean_text(card_id)

    response = (
        supabase
        .table("support_card_effects")
        .select("*")
        .eq("card_id", normalized_card_id)
        .execute()
    )

    effects = []

    for row in response.data or []:
        effect = {
            key: "" if value is None else value
            for key, value in dict(row).items()
        }

        effect["card_id"] = _as_clean_text(
            effect.get("card_id")
        )

        effects.append(effect)

    def effect_sort_key(effect):
        try:
            return int(_as_clean_text(
                effect.get("sort_order")
            ) or 0)
        except ValueError:
            return 0

    effects.sort(key=effect_sort_key)

    return effects


def split_event_title(title):
    title = title.strip()

    if title.startswith("(") and ")" in title:
        index = title.find(")")
        mark = title[:index + 1]
        clean_title = title[index + 1:].strip()

        return mark, clean_title

    return "", title


def parse_event_line(raw_line, skill_lookup):
    raw_line = raw_line.strip()
    line_type = "normal"

    # Dòng bắt đầu bằng ! sẽ được tô màu cam.
    # Ví dụ: !Randomly either, !or, !Event chain ended
    if raw_line.startswith("!"):
        line_type = "note"
        raw_line = raw_line[1:].strip()

    line = {
        "text": raw_line,
        "type": line_type,
        "prefix": "",
        "skill_name": "",
        "skill_id": "",
        "suffix": ""
    }

    # Dạng 1:
    # Mile Corners ○ hint +2
    hint_match = re.match(r"^(.+?)\s+hint\s+(.+)$", raw_line, re.IGNORECASE)

    if hint_match:
        skill_name = hint_match.group(1).strip()
        suffix = "hint " + hint_match.group(2).strip()

        normalized_skill_name = text_to_id(skill_name)
        skill_id = skill_lookup.get(normalized_skill_name, normalized_skill_name)

        line["skill_name"] = skill_name
        line["skill_id"] = skill_id
        line["suffix"] = suffix

        return line

    # Dạng 2:
    # Obtain Running Idle skill
    obtain_match = re.match(r"^Obtain\s+(.+?)\s+skill$", raw_line, re.IGNORECASE)

    if obtain_match:
        skill_name = obtain_match.group(1).strip()

        normalized_skill_name = text_to_id(skill_name)
        skill_id = skill_lookup.get(normalized_skill_name, normalized_skill_name)

        line["prefix"] = "Obtain"
        line["skill_name"] = skill_name
        line["skill_id"] = skill_id
        line["suffix"] = "skill"

        return line

    return line

def parse_event_choices(detail, skill_lookup):
    choices = []

    if detail is None:
        return choices

    # Dạng mới:
    # Top::...||Bot::...
    # Dạng cũ:
    # Speed +7|Power +7|Taiki Shuttle bond +5
    if "||" in detail or "::" in detail:
        choice_blocks = detail.split("||")
    else:
        choice_blocks = [detail]

    for block in choice_blocks:
        block = block.strip()

        if block == "":
            continue

        if "::" in block:
            label, lines_text = block.split("::", 1)
            label = label.strip()
        else:
            label = ""
            lines_text = block

        lines = []

        for raw_line in lines_text.split("|"):
            raw_line = raw_line.strip()

            if raw_line == "":
                continue

            lines.append(parse_event_line(raw_line, skill_lookup))

        choices.append({
            "label": label,
            "label_class": label.lower(),
            "lines": lines
        })

    return choices


def make_legacy_detail_lines(choices):
    detail_lines = []

    for choice in choices:
        label = choice.get("label", "")

        if label != "":
            detail_lines.append(label)

        for line in choice.get("lines", []):
            detail_lines.append(line.get("text", ""))

    return detail_lines


def load_support_card_training_events(card_id):
    """
    Đọc toàn bộ Training Events của một Support Card từ bảng
    public.support_card_training_events trên Supabase.

    Trả về:
    date_events, chain_events, random_events, special_events
    """
    grouped_events = {
        "date": [],
        "chain": [],
        "random": [],
        "special": []
    }

    normalized_card_id = _as_clean_text(card_id).lower()

    section_aliases = {
        "date": "date",
        "dates": "date",

        "chain": "chain",
        "chain_event": "chain",
        "chain_events": "chain",

        "random": "random",
        "random_event": "random",
        "random_events": "random",

        "special": "special",
        "special_event": "special",
        "special_events": "special"
    }

    response = (
        supabase
        .table("support_card_training_events")
        .select(
            "card_id, section, event_id, title, detail, sort_order"
        )
        .eq("card_id", normalized_card_id)
        .execute()
    )

    for row in response.data or []:
        row_card_id = _as_clean_text(
            row.get("card_id")
        ).lower()

        raw_section = _as_clean_text(
            row.get("section")
        ).lower()

        section = section_aliases.get(raw_section)

        if section is None:
            current_app.logger.warning(
                "[TRAINING EVENTS] Bỏ qua section không hợp lệ: %s",
                raw_section
            )
            continue

        try:
            sort_order = int(
                _as_clean_text(row.get("sort_order")) or 0
            )
        except ValueError:
            sort_order = 0

        event = {
            "card_id": row_card_id,
            "section": section,
            "event_id": _as_clean_text(
                row.get("event_id")
            ),
            "title": _as_clean_text(
                row.get("title")
            ),
            "detail": _as_clean_text(
                row.get("detail")
            ),
            "sort_order": sort_order
        }

        grouped_events[section].append(event)

    for section_name in grouped_events:
        grouped_events[section_name].sort(
            key=lambda event: event["sort_order"]
        )

    current_app.logger.info(
        "[TRAINING EVENTS] card_id=%s | date=%s | chain=%s | "
        "random=%s | special=%s",
        normalized_card_id,
        len(grouped_events["date"]),
        len(grouped_events["chain"]),
        len(grouped_events["random"]),
        len(grouped_events["special"])
    )

    return (
        grouped_events["date"],
        grouped_events["chain"],
        grouped_events["random"],
        grouped_events["special"]
    )
