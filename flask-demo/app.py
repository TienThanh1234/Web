import csv
import os
import re
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "Mashkyrielight@!#1234567890"
)

USERS_FILE = BASE_DIR / "users.csv"
RACES_CSV = BASE_DIR / "races.csv"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY", "").strip()
    or os.environ.get("SUPABASE_ANON_KEY", "").strip()
)

if not SUPABASE_URL:
    raise RuntimeError(
        "Thiếu SUPABASE_URL trong file .env hoặc biến môi trường."
    )

if not SUPABASE_KEY:
    raise RuntimeError(
        "Thiếu SUPABASE_KEY hoặc SUPABASE_ANON_KEY "
        "trong file .env hoặc biến môi trường."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

# =========================
# COMMON HELPERS
# =========================

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def make_short_description(text):
    if text is None:
        return ""

    # Xóa mọi đoạn nằm trong ngoặc vuông: [...]
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
    page_size=1000
):
    """Đọc toàn bộ dữ liệu Supabase theo từng trang."""
    rows = []
    start = 0

    while True:
        query = supabase.table(table_name).select("*")

        if order_column:
            query = query.order(order_column)

        response = (
            query
            .range(start, start + page_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    return rows


# =========================
# ACCOUNT HELPERS
# =========================

def ensure_users_file():
    """Tạo users.csv và tài khoản admin mặc định nếu file chưa tồn tại."""
    if os.path.exists(USERS_FILE):
        return

    with open(USERS_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["username", "password_hash"]
        )
        writer.writeheader()
        writer.writerow({
            "username": "admin",
            "password_hash": generate_password_hash("123")
        })


def load_users():
    ensure_users_file()
    users = []

    with open(USERS_FILE, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            username = (row.get("username") or "").strip()
            password_hash = (row.get("password_hash") or "").strip()

            if username == "" or password_hash == "":
                continue

            users.append({
                "username": username,
                "password_hash": password_hash
            })

    return users


def find_user(username):
    normalized_username = username.strip().lower()

    for user in load_users():
        if user["username"].lower() == normalized_username:
            return user

    return None


def create_user(username, password):
    ensure_users_file()

    with open(USERS_FILE, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["username", "password_hash"]
        )
        writer.writerow({
            "username": username,
            "password_hash": generate_password_hash(password)
        })

# =========================
# RACES
# =========================
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


app.jinja_env.filters["linkify_races"] = linkify_race_names


def load_items_by_id():
    """Tạo bảng tra cứu Item theo id từ Supabase."""
    items = load_items()

    return {
        item.get("id", "").strip(): item
        for item in items
        if item.get("id", "").strip()
    }


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
# =========================
# CHARACTER
# =========================

CHARACTER_SKILL_FIELDS = [
    "unique_skill_ids",
    "innate_skill_ids",
    "event_skill_ids",
    "awakening_lvl2_skill_id",
    "awakening_lvl2_highlight",
    "awakening_lvl2_items",
    "awakening_lvl3_skill_id",
    "awakening_lvl3_highlight",
    "awakening_lvl3_items",
    "awakening_lvl4_skill_id",
    "awakening_lvl4_highlight",
    "awakening_lvl4_items",
    "awakening_lvl5_skill_id",
    "awakening_lvl5_highlight",
    "awakening_lvl5_items",
]


def load_characters():
    character_list = []

    with open("characters.csv", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            row["id"] = int(row["id"])
            row["rarity"] = int(row["rarity"])

            # characters.csv chưa có các cột unique_skill_ids /
            # innate_skill_ids / awakening_lvlN_... thì tự điền rỗng,
            # để trang chi tiết không bị lỗi và chỉ đơn giản là không
            # hiển thị mấy mục đó cho tới khi bạn bổ sung dữ liệu.
            for field_name in CHARACTER_SKILL_FIELDS:
                row.setdefault(field_name, "")

            character_list.append(row)

    return character_list


def load_character_details():
    character_detail_list = []

    with open("character_detail.csv", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            row["id"] = int(row["id"])
            row["rarity"] = int(row["rarity"])
            character_detail_list.append(row)

    return character_detail_list


# =========================
# CHARACTER EPITHETS / SKILLS / AWAKENINGS
# =========================

def load_character_epithets(character_slug):
    """
    Đọc Epithet của 1 character từ character_epithets.csv.
    Nhiều dòng cùng 'title' sẽ được gộp thành 1 epithet với danh sách requirement.
    """
    rows = read_csv_file("character_epithets.csv")

    grouped = {}
    title_order = []

    for row in rows:
        if row.get("character_slug", "").strip() != character_slug:
            continue

        title = row.get("title", "").strip()

        if title == "":
            continue

        if title not in grouped:
            grouped[title] = []
            title_order.append(title)

        requirement = row.get("requirement", "").strip()

        if requirement != "":
            grouped[title].append(requirement)

    return [
        {"title": title, "requirements": grouped[title]}
        for title in title_order
    ]


def get_character_unique_skills(character):
    """
    Trả về các bậc (tier) của Unique Skill, kèm nhãn số sao.

    Danh sách skill id được lấy thẳng từ cột 'unique_skill_ids' của
    chính character (characters.csv) - không qua bảng quan hệ nào cả.
    Dữ liệu chi tiết skill (tên, icon, mô tả...) luôn được đọc từ
    bảng public.skills trên Supabase qua get_skills_by_ids().

    Skill gốc (index 0) hiển thị "★ and ★★", mỗi bản nâng cấp
    tiếp theo tăng thêm 1 sao (★★★+, ★★★★+, ...), giống quy ước của game.
    """
    skill_ids_text = character.get("unique_skill_ids", "")
    skills = get_skills_by_ids(skill_ids_text)

    tiers = []

    for index, skill in enumerate(skills):
        if index == 0:
            star_label = "★ and ★★"
        else:
            star_label = ("★" * (index + 2)) + "+"

        tiers.append({
            "star_label": star_label,
            "skill": skill
        })

    return tiers


def get_character_innate_skills(character):
    """
    Trả về danh sách Innate Skill.

    Danh sách skill id lấy từ cột 'innate_skill_ids' của character
    (characters.csv), dữ liệu chi tiết skill lấy từ Supabase.
    """
    return get_skills_by_ids(character.get("innate_skill_ids", ""))


def get_character_awakenings(character):
    """
    Trả về danh sách Awakening Skill theo từng level (2-5).

    Mỗi level đọc 3 cột trên chính character (characters.csv):
    awakening_lvlN_skill_id, awakening_lvlN_highlight, awakening_lvlN_items.
    - Skill (tên, icon, mô tả) lấy từ Supabase qua get_skills_by_ids().
    - Item icon (Racing Shoes, Winner's Sash, ...) cũng lấy từ Supabase
      qua load_items_by_id().
    """
    items_by_id = load_items_by_id()
    awakenings = []

    for level in range(2, 6):
        prefix = f"awakening_lvl{level}_"

        skill_id = character.get(prefix + "skill_id", "").strip()
        skill = None

        if skill_id != "":
            matched_skills = get_skills_by_ids(skill_id)
            skill = matched_skills[0] if matched_skills else None

        item_ids = [
            item_id.strip()
            for item_id in character.get(prefix + "items", "").split("|")
            if item_id.strip()
        ]

        items = [
            items_by_id.get(
                item_id,
                {
                    "id": item_id,
                    "name": item_id,
                    "image": "",
                    "description": "",
                    "uses": "",
                    "how_to_get": ""
                }
            )
            for item_id in item_ids
        ]

        if skill is None and not items:
            continue

        awakenings.append({
            "level": level,
            "skill": skill,
            "highlight": character.get(
                prefix + "highlight", ""
            ).strip().lower() == "yes",
            # Lưu ý: đặt tên là 'materials' chứ không phải 'items',
            # vì 'items' trùng với method dict.items() có sẵn -> Jinja
            # sẽ lấy nhầm cái method đó thay vì list dữ liệu của mình.
            "materials": items
        })

    return awakenings


def get_character_event_skills(character):
    """
    Trả về danh sách Skill from events (skill nhận được qua training event).

    Danh sách skill id lấy từ cột 'event_skill_ids' của character
    (characters.csv), dữ liệu chi tiết skill lấy từ Supabase - giống hệt
    cách làm với Innate Skill.
    """
    return get_skills_by_ids(character.get("event_skill_ids", ""))


SCHEDULE_HALF_LABELS = {
    "first half": "Early",
    "second half": "Late",
}


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


def get_character_objectives(character_slug):
    """
    Trả về danh sách Objective (mốc đua bắt buộc) của 1 character.

    Thứ tự, turn và yêu cầu (Place 1st / Participate in / ...) đọc từ
    character_objectives.csv - vì đây là dữ liệu riêng theo từng
    character (cùng 1 race có thể xuất hiện ở turn khác nhau tùy
    character). Dữ liệu race thật (ảnh, grade, sân đua, cự ly, tháng...)
    lấy từ bảng public.races trên Supabase qua get_races_by_slugs().
    """
    rows = [
        row
        for row in read_csv_file("character_objectives.csv")
        if row.get("character_slug", "").strip() == character_slug
    ]

    def sort_key(row):
        try:
            return int(row.get("sort_order", "") or 0)
        except ValueError:
            return 0

    rows.sort(key=sort_key)

    races_by_slug = get_races_by_slugs(
        [row.get("race_slug", "") for row in rows]
    )

    objectives = []
    previous_turn = None

    for index, row in enumerate(rows, start=1):
        race_slug = row.get("race_slug", "").strip()
        race = races_by_slug.get(race_slug, {})

        try:
            turn = int(row.get("turn", "") or 0)
        except ValueError:
            turn = 0

        if previous_turn is None:
            turn_label = f"Turn {turn}"
        else:
            turn_label = f"Turn {turn} (previous + {turn - previous_turn})"

        previous_turn = turn

        half_key = race.get("schedule_half", "").strip().lower()
        half_label = SCHEDULE_HALF_LABELS.get(
            half_key,
            race.get("schedule_half", "")
        )

        month_label = " ".join(
            part
            for part in [half_label, race.get("schedule_month", "")]
            if part
        )

        distance_m = race.get("distance_m", "")

        info_parts = [
            race.get("grade", ""),
            race.get("terrain", ""),
            (distance_m + "m") if distance_m else "",
            race.get("distance_type", "")
        ]
        info_line = " – ".join(part for part in info_parts if part)

        objectives.append({
            "index": index,
            "requirement": row.get("requirement", "").strip(),
            "race_slug": race_slug,
            "race_name": race.get("name", race_slug),
            "race_image": race.get("image", ""),
            "turn_label": turn_label,
            "class_label": race.get("career_class", ""),
            "month_label": month_label,
            "info_line": info_line
        })

    return objectives


CHARACTER_TRAINING_EVENT_GROUPS = [
    ("costume", "Costume Events"),
    ("choices", "Events With Choices"),
    ("date", "Date Events"),
    ("secret", "Secret Events"),
    ("special", "Special Events"),
    ("after_race", "After a Race"),
    ("no_choices", "Events Without Choices"),
]


def load_character_training_events(character_slug):
    """
    Đọc Training Events của 1 character từ character_training_events.csv,
    gom nhóm theo cột 'group' (costume / choices / date / secret).

    Cột 'detail' dùng chung 1 cú pháp với Training Events của Support
    Card (xem render_raw_event_choices trong character_detail.html):
    - '||' tách các khối lựa chọn (Top / Bot)
    - '::' tách nhãn lựa chọn và nội dung, ví dụ "Top::Speed +10|..."
    - '|' xuống dòng trong 1 khối
    - dòng bắt đầu bằng '!' sẽ được tô màu note (cam)
    """
    rows = read_csv_file("character_training_events.csv")

    grouped = {group_key: [] for group_key, _ in CHARACTER_TRAINING_EVENT_GROUPS}

    for row in rows:
        if row.get("character_slug", "").strip() != character_slug:
            continue

        group_key = row.get("group", "").strip().lower()

        if group_key not in grouped:
            continue

        try:
            sort_order = int(row.get("sort_order", "") or 0)
        except ValueError:
            sort_order = 0

        grouped[group_key].append({
            "event_id": row.get("event_id", "").strip(),
            "title": row.get("title", "").strip(),
            "detail": row.get("detail", ""),
            "sort_order": sort_order
        })

    for group_key in grouped:
        grouped[group_key].sort(key=lambda event: event["sort_order"])

    return grouped


# =========================
# SKILLS
# =========================

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


def get_skills_by_ids(skill_ids_text, highlight_ids_text=""):
    skills = load_skills()

    skill_map = {}

    for skill in skills:
        skill_map[skill["id"]] = skill

    selected_skills = []

    if skill_ids_text is None:
        return selected_skills

    skill_ids = skill_ids_text.split("|")

    highlight_ids = []

    if highlight_ids_text is not None and highlight_ids_text.strip() != "":
        for highlight_id in highlight_ids_text.split("|"):
            highlight_ids.append(highlight_id.strip())

    for skill_id in skill_ids:
        skill_id = skill_id.strip()

        if skill_id == "":
            continue

        if skill_id not in skill_map:
            continue

        skill = skill_map[skill_id].copy()

        if skill_id in highlight_ids:
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


# =========================
# SUPPORT CARD
# =========================

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
            app.logger.warning(
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

    app.logger.info(
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

# =========================
# ITEMS
# =========================
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

# =========================
# HOME
# =========================

@app.route("/")
@app.route("/home")
def home():
    return render_template(
        "home.html",
        username=session.get("username")
    )


# =========================
# AUTHENTICATION
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == "" or password == "":
            return render_template(
                "login.html",
                error="Please enter both username and password.",
                entered_username=username
            )

        user = find_user(username)

        if user is None or not check_password_hash(
            user["password_hash"],
            password
        ):
            return render_template(
                "login.html",
                error="Wrong username or password.",
                entered_username=username
            )

        session["username"] = user["username"]

        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "username" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            return render_template(
                "register.html",
                error=(
                    "Username must be 3-30 characters and contain only "
                    "letters, numbers, or underscores."
                ),
                entered_username=username
            )

        if len(password) < 6:
            return render_template(
                "register.html",
                error="Password must contain at least 6 characters.",
                entered_username=username
            )

        if password != confirm_password:
            return render_template(
                "register.html",
                error="The confirmation password does not match.",
                entered_username=username
            )

        if find_user(username) is not None:
            return render_template(
                "register.html",
                error="This username is already registered.",
                entered_username=username
            )

        create_user(username, password)
        session["username"] = username

        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# =========================
# CHARACTER ROUTES
# =========================

@app.route("/characters")
@login_required
def characters():
    character_list = load_characters()
    return render_template("characters.html", characters=character_list)


@app.route("/characters/<slug>")
@login_required
def character_detail(slug):
    character_list = load_characters()

    for character in character_list:
        if character.get("slug", "") == slug:
            return render_template(
                "character_detail.html",
                character=character,
                epithets=load_character_epithets(slug),
                unique_skills=get_character_unique_skills(character),
                innate_skills=get_character_innate_skills(character),
                event_skills=get_character_event_skills(character),
                awakenings=get_character_awakenings(character),
                objectives=get_character_objectives(slug),
                training_events=load_character_training_events(slug),
                training_event_groups=CHARACTER_TRAINING_EVENT_GROUPS
            )

    return "Character not found", 404


# =========================
# SKILL ROUTES
# =========================

@app.route("/skills")
@login_required
def skills():
    categories, grouped_skills = group_skills_by_category()

    return render_template(
        "skills.html",
        categories=categories,
        grouped_skills=grouped_skills
    )


@app.route("/skills/<skill_id>")
@login_required
def skill_detail(skill_id):
    skill = get_skill_detail(skill_id)

    if skill is None:
        abort(404)

    return render_template("skill_detail.html", skill=skill)


# =========================
# SUPPORT CARD ROUTES
# =========================

@app.route("/support-card")
@app.route("/supports")
@login_required
def support_card():
    try:
        support_cards = load_support_cards()

        return render_template(
            "support_card.html",
            support_cards=support_cards
        )

    except Exception:
        app.logger.exception(
            "Không thể tải danh sách Support Card từ Supabase."
        )

        return render_template(
            "support_card.html",
            support_cards=[],
            load_error=(
                "Không thể tải dữ liệu Support Card từ Supabase. "
                "Hãy kiểm tra bảng, key và RLS policy."
            )
        ), 500


@app.route("/support-card/<card_id>")
@app.route("/supports/<card_id>")
@login_required
def support_detail(card_id):
    try:
        card = get_support_card_by_id(card_id)

        if card is None:
            abort(404)

        effects = load_support_card_effects(card_id)

        (
            date_events,
            chain_events,
            random_events,
            special_events
        ) = load_support_card_training_events(card_id)

        # Skills hiện được đọc từ bảng public.skills trên Supabase.
        hint_skills = get_skills_by_ids(
            card.get("hint_skill_ids", ""),
            card.get("highlight_skill_ids", "")
        )

        event_skills = get_skills_by_ids(
            card.get("event_skill_ids", ""),
            card.get("highlight_skill_ids", "")
        )

        stat_gain_list = []
        stat_gain_text = card.get("stat_gain", "")

        if stat_gain_text.strip() != "":
            stat_gain_list = stat_gain_text.split("|")

        return render_template(
            "support_card_details.html",
            card=card,
            effects=effects,
            hint_skills=hint_skills,
            event_skills=event_skills,
            stat_gain_list=stat_gain_list,
            chain_events=chain_events,
            random_events=random_events,
            date_events=date_events,
            special_events=special_events
        )

    except Exception as error:
        # Không biến lỗi 404 thành lỗi 500.
        if getattr(error, "code", None) == 404:
            raise

        app.logger.exception(
            "Không thể tải chi tiết Support Card %s từ Supabase.",
            card_id
        )

        return (
            "Không thể tải chi tiết Support Card từ Supabase. "
            "Hãy kiểm tra bảng, dữ liệu khóa ngoại và RLS policy.",
            500
        )

# =========================
# ITEMS ROUTES
# =========================

@app.route("/items")
@login_required
def items():
    try:
        item_rows = load_items()

        return render_template(
            "items.html",
            items=item_rows
        )

    except Exception:
        app.logger.exception(
            "Không thể tải Items từ Supabase."
        )

        return render_template(
            "items.html",
            items=[],
            load_error=(
                "Không thể tải dữ liệu Items từ Supabase. "
                "Hãy kiểm tra bảng items và RLS policy."
            )
        ), 500


@app.route("/items/<item_id>")
@login_required
def item_detail(item_id):
    item = get_item_by_id(item_id)

    if item is None:
        abort(404)

    return render_template("item_detail.html", item=item)

# =========================
# RACES ROUTES
# =========================

@app.route("/races")
def races():
    race_list = load_races()

    racetracks = sorted({
        race["racetrack"]
        for race in race_list
        if race.get("racetrack") and race["racetrack"] != "Varies"
    })

    return render_template(
        "races.html",
        races=race_list,
        racetracks=racetracks
    )

@app.route("/races/<slug>")
def race_detail(slug):
    race = next(
        (
            race
            for race in load_races()
            if race.get("slug", "").strip() == slug
        ),
        None
    )

    if race is None:
        abort(404)

    rewards = load_race_rewards(slug)
    fans = load_race_fans(slug)

    return render_template(
        "races_detail.html",
        race=race,
        rewards=rewards,
        fans=fans
    )
# =========================
# OTHER ROUTES
# =========================

@app.route("/banner-history")
@login_required
def banner_history():
    return render_template("banner_history.html")



# Giữ đường dẫn cũ để tránh lỗi các link chưa sửa
@app.route("/item")
@login_required
def item():
    return redirect(url_for("items"))


@app.route("/cm-guide")
@login_required
def cm_guide():
    return render_template("cm_guide.html")


@app.route("/scenario-guide")
@login_required
def scenario_guide():
    return render_template("scenario_guide.html")


if __name__ == "__main__":
    app.run(debug=True)