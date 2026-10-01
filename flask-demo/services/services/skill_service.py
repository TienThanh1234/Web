"""Skills data access (Supabase)."""
from utils import (
    fetch_all_supabase_rows,
    make_short_description,
    normalize_supabase_row,
    text_to_id,
)


def load_skills():
    """Đọc toàn bộ Skills từ bảng public.skills trên Supabase."""
    raw_rows = fetch_all_supabase_rows(
        "skills",
        order_column="id"
    )

    skills = []

    for raw_row in raw_rows:
        row = normalize_supabase_row(raw_row)

        if row.get("id", "") == "":
            continue

        category = row.get("category", "")

        if category == "":
            if row.get("rarity", "").lower() == "negative":
                category = "negative"
            else:
                category = "passive"

        row["category"] = category.lower()
        row["base_duration"] = row.get("base_duration", "")
        row["short_description"] = make_short_description(
            row.get("description", "")
        )
        row["display_name"] = row.get("name", "")

        skills.append(row)

    return skills


def _normalize_skill_key(value):
    """Chuẩn hóa id/tên skill để so khớp (crawler vs Supabase)."""
    if value is None:
        return ""
    key = text_to_id(str(value))
    # biến thể thường gặp
    key = key.replace("__", "_").strip("_")
    return key


def get_skills_by_ids(skill_ids_text, highlight_ids_text=""):
    """
    Tra skill theo id trong characters.csv.

    Khớp theo thứ tự:
      1. id đúng trên Supabase
      2. text_to_id(name)
      3. text_to_id(id) nếu id có ký tự lạ
      4. vài alias đơn giản (oo/o, bỏ hậu tố ready, ...)
    """
    skills = load_skills()

    skill_map = {}

    def register(key, skill):
        key = _normalize_skill_key(key)
        if key and key not in skill_map:
            skill_map[key] = skill

    for skill in skills:
        sid = skill.get("id", "")
        name = skill.get("name", "")
        register(sid, skill)
        register(name, skill)
        # giữ bản gốc (không normalize) để khớp exact cũ
        if sid and sid not in skill_map:
            skill_map[sid] = skill

    selected_skills = []

    if skill_ids_text is None:
        return selected_skills

    skill_ids = str(skill_ids_text).split("|")

    highlight_ids = set()
    if highlight_ids_text is not None and str(highlight_ids_text).strip() != "":
        for highlight_id in str(highlight_ids_text).split("|"):
            h = highlight_id.strip()
            if h:
                highlight_ids.add(h)
                highlight_ids.add(_normalize_skill_key(h))

    def resolve(raw_id):
        raw_id = raw_id.strip()
        if not raw_id:
            return None
        # exact
        if raw_id in skill_map:
            return skill_map[raw_id]
        norm = _normalize_skill_key(raw_id)
        if norm in skill_map:
            return skill_map[norm]
        # thử vài biến thể
        variants = {
            norm.replace("_o", "_oo"),
            norm.replace("_oo", "_o"),
            norm.replace("_ready", ""),
            norm + "_ready",
            norm.rstrip("_o").rstrip("_oo"),
        }
        for v in variants:
            v = _normalize_skill_key(v)
            if v in skill_map:
                return skill_map[v]
        return None

    for skill_id in skill_ids:
        skill_id = skill_id.strip()
        if skill_id == "":
            continue

        matched = resolve(skill_id)
        if matched is None:
            # giữ placeholder để biết CSV có id nhưng Supabase thiếu / lệch tên
            selected_skills.append({
                "id": skill_id,
                "name": skill_id.replace("_", " ").title(),
                "image": "",
                "description": f"(Skill not found in database: {skill_id})",
                "short_description": f"Missing: {skill_id}",
                "category": "unknown",
                "rarity": "",
                "display_name": skill_id.replace("_", " ").title(),
                "highlight": "yes" if (
                    skill_id in highlight_ids
                    or _normalize_skill_key(skill_id) in highlight_ids
                ) else "no",
                "_missing": True,
            })
            continue

        skill = matched.copy()
        if (
            skill_id in highlight_ids
            or _normalize_skill_key(skill_id) in highlight_ids
            or skill.get("id", "") in highlight_ids
        ):
            skill["highlight"] = "yes"
        else:
            skill["highlight"] = "no"
        selected_skills.append(skill)

    return selected_skills


def group_skills_by_category():
    skills = load_skills()

    categories = [
        {
            "id": "buff",
            "name": "Buff",
            "section_title": "Buff Skills",
            "icon": "category_buff.png"
        },
        {
            "id": "debuff",
            "name": "Debuff",
            "section_title": "Debuff Skills",
            "icon": "category_debuff.png"
        },
        {
            "id": "recovery",
            "name": "Recovery",
            "section_title": "Recovery Skills",
            "icon": "category_recovery.png"
        },
        {
            "id": "passive",
            "name": "Passive",
            "section_title": "Passive Skills",
            "icon": "category_passive.png"
        },
        {
            "id": "negative",
            "name": "Negative",
            "section_title": "Negative Skills",
            "icon": "category_negative.png"
        },
        {
            "id": "unique",
            "name": "Unique",
            "section_title": "Unique",
            "icon": "category_unique.png"
        }
    ]

    grouped_skills = {}

    for category in categories:
        grouped_skills[category["id"]] = []

    for skill in skills:
        category_id = skill.get("category", "").strip().lower()

        if category_id == "":
            category_id = "passive"

        if category_id not in grouped_skills:
            grouped_skills[category_id] = []

        grouped_skills[category_id].append(skill)

    return categories, grouped_skills


def get_skill_detail(skill_id):
    skills = load_skills()

    selected_skill = None

    for skill in skills:
        if skill["id"] == skill_id:
            selected_skill = skill
            break

    if selected_skill is None:
        return None

    # Nếu lỡ mở trực tiếp một upgrade skill,
    # thì tự chuyển về skill gốc để không bị trang riêng.
    if selected_skill.get("type") == "upgrade" and selected_skill.get("parent_id"):
        parent_id = selected_skill["parent_id"]

        for skill in skills:
            if skill["id"] == parent_id:
                selected_skill = skill
                break

    selected_skill["upgraded_skills"] = []

    is_negative_skill = (
        selected_skill.get("category", "").strip().lower() == "negative"
        or selected_skill.get("rarity", "").strip().lower() == "negative"
    )

    if selected_skill.get("type") == "normal" and not is_negative_skill:
        for skill in skills:
            if (
                skill.get("type") == "upgrade"
                and skill.get("parent_id") == selected_skill["id"]
            ):
                selected_skill["upgraded_skills"].append(skill)

    return selected_skill


def make_skill_lookup_by_name():
    skill_lookup = {}

    for skill in load_skills():
        name = skill.get("name", "").strip()
        skill_id = skill.get("id", "").strip()

        if name != "" and skill_id != "":
            skill_lookup[text_to_id(name)] = skill_id

    return skill_lookup

