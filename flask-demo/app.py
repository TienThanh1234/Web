import csv
import re
from flask import Flask, abort, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "Mashkyrielight@!#1234567890"


def make_short_description(text):
    if text is None:
        return ""

    # Xóa mọi đoạn nằm trong ngoặc vuông: [...]
    text = re.sub(r"\s*\[[^\]]*\]", "", text)

    return text.strip()


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
# SUPPORT CARD
# =========================

def load_support_cards():
    support_cards = []

    with open("support_cards.csv", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            # Nếu chưa có thumb_image thì tự dùng image luôn
            if row.get("thumb_image") is None or row.get("thumb_image", "").strip() == "":
                row["thumb_image"] = row.get("image", "")

            row["hint_skill_ids"] = row.get("hint_skill_ids", "")
            row["event_skill_ids"] = row.get("event_skill_ids", "")
            row["highlight_skill_ids"] = row.get("highlight_skill_ids", "")
            row["stat_gain"] = row.get("stat_gain", "")
            row["stat_icon"] = row.get("stat_icon", "")
            row["random_events"] = row.get("random_events", "")

            support_cards.append(row)

    return support_cards


def load_support_card_effects(card_id):
    effects = []

    with open("support_card_effects.csv", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("card_id", "").strip() == card_id:
                effects.append(row)

    return effects

def load_support_card_training_events(card_id):
    chain_events = []
    random_events = []

    with open("support_card_training_events.csv", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("card_id", "").strip() != card_id:
                continue

            row["section"] = row.get("section", "").strip().lower()
            row["event_id"] = row.get("event_id", "").strip()
            row["title"] = row.get("title", "").strip()
            row["detail"] = row.get("detail", "")
            row["sort_order"] = int(row.get("sort_order", 0))

            detail_lines = []

            for line in row["detail"].split("|"):
                line = line.strip()

                if line != "":
                    detail_lines.append(line)

            row["detail_lines"] = detail_lines

            if row["section"] == "chain":
                chain_events.append(row)
            elif row["section"] == "random":
                random_events.append(row)

    chain_events.sort(key=lambda event: event["sort_order"])
    random_events.sort(key=lambda event: event["sort_order"])

    return chain_events, random_events


# =========================
# SKILLS
# =========================

def load_skills():
    skills = []

    with open("skills.csv", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if not row.get("id"):
                continue

            category = row.get("category", "")

            if category is None or category.strip() == "":
                if row.get("rarity", "").strip().lower() == "negative":
                    category = "negative"
                else:
                    category = "passive"

            row["category"] = category.strip().lower()

            row["base_duration"] = row.get("base_duration", "")
            if row["base_duration"] is None:
                row["base_duration"] = ""
            row["base_duration"] = row["base_duration"].strip()

            row["short_description"] = make_short_description(row.get("description", ""))
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


def get_normal_skills():
    skills = load_skills()
    normal_skills = []

    for skill in skills:
        if skill.get("type", "") == "normal":
            normal_skills.append(skill)

    return normal_skills


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


# =========================
# LOGIN
# =========================

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == "admin" and password == "123":
            session["username"] = username
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="Wrong username or password")

    return render_template("login.html")


@app.route("/home")
def home():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    return render_template("home.html", username=username)


# =========================
# CHARACTER ROUTES
# =========================

@app.route("/characters")
def characters():
    if "username" not in session:
        return redirect(url_for("login"))

    character_list = load_characters()
    return render_template("characters.html", characters=character_list)


@app.route("/characters/<slug>")
def character_detail(slug):
    if "username" not in session:
        return redirect(url_for("login"))

    character_list = load_characters()

    for character in character_list:
        if character.get("slug", "") == slug:
            return render_template("character_detail.html", character=character)

    return "Character not found", 404


# =========================
# SKILL ROUTES
# =========================

@app.route("/skills")
def skills():
    if "username" not in session:
        return redirect(url_for("login"))

    categories, grouped_skills = group_skills_by_category()

    return render_template(
        "skills.html",
        categories=categories,
        grouped_skills=grouped_skills
    )


@app.route("/skills/<skill_id>")
def skill_detail(skill_id):
    if "username" not in session:
        return redirect(url_for("login"))

    skill = get_skill_detail(skill_id)

    if skill is None:
        abort(404)

    return render_template("skill_detail.html", skill=skill)


# =========================
# SUPPORT CARD ROUTES
# =========================

@app.route("/support-card")
@app.route("/supports")
def support_card():
    if "username" not in session:
        return redirect(url_for("login"))

    support_cards = load_support_cards()

    return render_template(
        "support_card.html",
        support_cards=support_cards
    )


@app.route("/support-card/<card_id>")
@app.route("/supports/<card_id>")
def support_detail(card_id):
    if "username" not in session:
        return redirect(url_for("login"))

    support_cards = load_support_cards()

    card = None

    for item in support_cards:
        if item.get("id", "").strip() == card_id:
            card = item
            break

    if card is None:
        abort(404)

    effects = load_support_card_effects(card_id)
    chain_events, random_events = load_support_card_training_events(card_id)

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

    if stat_gain_text is not None and stat_gain_text.strip() != "":
        stat_gain_list = stat_gain_text.split("|")

    return render_template(
        "support_card_details.html",
        card=card,
        effects=effects,
        hint_skills=hint_skills,
        event_skills=event_skills,
        stat_gain_list=stat_gain_list,
        chain_events=chain_events,
        random_events=random_events
    )


# =========================
# OTHER ROUTES
# =========================

@app.route("/banner-history")
def banner_history():
    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("banner_history.html")


@app.route("/tier-list")
def tier_list():
    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("tier_list.html")


@app.route("/cm-guide")
def cm_guide():
    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("cm_guide.html")


@app.route("/scenario-guide")
def scenario_guide():
    if "username" not in session:
        return redirect(url_for("login"))

    return render_template("scenario_guide.html")


if __name__ == "__main__":
    app.run(debug=True)