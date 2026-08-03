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

def load_characters():
    character_list = []

    with open("characters.csv", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            row["id"] = int(row["id"])
            row["rarity"] = int(row["rarity"])
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
            return render_template("character_detail.html", character=character)

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
