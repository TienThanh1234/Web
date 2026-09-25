"""Character data access (CSV + related lookups)."""
import csv
import re

from services.item_service import load_items_by_id
from services.race_service import get_races_by_slugs, load_races
from services.skill_service import get_skills_by_ids
from utils import fetch_all_supabase_rows, normalize_supabase_row, read_csv_file


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

SCHEDULE_HALF_LABELS = {
    "first half": "Early",
    "second half": "Late",
}

# CSV cũ crawl sai: race_slug trống + "Place 3000th or better in" = fan goal
_FAN_PLACE_RE = re.compile(
    r"^Place\s+(\d+)(?:st|nd|rd|th)\s+or\s+better\s+in\s*$",
    re.I,
)

CHARACTER_TRAINING_EVENT_GROUPS = [
    ("costume", "Costume Events"),
    ("choices", "Events With Choices"),
    ("date", "Date Events"),
    ("secret", "Secret Events"),
    ("special", "Special Events"),
    ("after_race", "After a Race"),
    ("no_choices", "Events Without Choices"),
]

RACE_SLUG_ALIASES = {
    "tokyo_yushun_japan_derby": "tokyo_yushun_japanese_derby",
    "tokyo-yushun-japan-derby": "tokyo_yushun_japanese_derby",
    "kikka_sho": "kikuka_sho",
    "kikka-sho": "kikuka_sho",
    "kikuka-sho": "kikuka_sho",
    "tenno-sho-spring": "tenno_sho_spring",
    "tenno-sho-autumn": "tenno_sho_autumn",
    "japan-cup": "japan_cup",
    "arima-kinen": "arima_kinen",
    "yasuda-kinen": "yasuda_kinen",
    "satsuki-sho": "satsuki_sho",
    "hopeful-stakes": "hopeful_stakes",
    "takamatsunomiya-kinen": "takamatsunomiya_kinen",
    "sprinters-stakes": "sprinters_stakes",
    "junior-make-debut": "junior_make_debut",
    # Mile Championship Nambu Hai — races.csv slug rút gọn
    "mile_championship_nambu_hai": "m_c_nambu_hai",
    "mile-championship-nambu-hai": "m_c_nambu_hai",
    "nambu_hai": "m_c_nambu_hai",
    "mc_nambu_hai": "m_c_nambu_hai",
    "m_c_nambu_hai": "m_c_nambu_hai",
}


def load_characters():
    """
    Đọc Characters từ Supabase (bảng public.characters).
    Pattern giống load_skills() — nếu Supabase rỗng thì fallback CSV.
    """
    raw_rows = fetch_all_supabase_rows(
        "characters",
        order_column="id",
    )

    character_list = []

    for raw_row in raw_rows:
        row = normalize_supabase_row(raw_row)

        # Bỏ dòng không có slug (không mở detail được)
        slug = (row.get("slug") or "").strip()
        if slug == "":
            continue
        row["slug"] = slug

        try:
            row["id"] = int(float(row.get("id") or 0))
        except (TypeError, ValueError):
            row["id"] = 0

        try:
            row["rarity"] = int(float(row.get("rarity") or 0))
        except (TypeError, ValueError):
            row["rarity"] = 0

        for field_name in CHARACTER_SKILL_FIELDS:
            if field_name not in row or row[field_name] is None:
                row[field_name] = ""

        character_list.append(row)

    # Fallback: data/characters.csv hoặc root characters.csv
    if not character_list:
        print(
            "[characters] Supabase 0 dòng — đọc CSV trong thư mục data/ (hoặc root)."
        )
        for row in read_csv_file("characters.csv"):
            try:
                row["id"] = int(float(row.get("id") or 0))
            except (TypeError, ValueError):
                row["id"] = 0
            try:
                row["rarity"] = int(float(row.get("rarity") or 0))
            except (TypeError, ValueError):
                row["rarity"] = 0
            for field_name in CHARACTER_SKILL_FIELDS:
                row.setdefault(field_name, "")
            if (row.get("slug") or "").strip():
                character_list.append(row)

    return character_list



def character_lookup_slugs(character_slug, character=None):
    """
    Tra objectives / training events theo slug costume HOẶC base.

    characters.csv: special-week-special-dreamer
    events CSV:     special-week  (hoặc full costume slug)
    """
    candidates = []
    seen = set()

    def add(s):
        s = (s or "").strip()
        if s and s not in seen:
            seen.add(s)
            candidates.append(s)

    add(character_slug)

    if character:
        url_name = (
            character.get("gametora_url_name")
            or character.get("url_name")
            or ""
        ).strip()
        if re.match(r"^\d+-", url_name):
            add(re.sub(r"^\d+-", "", url_name))

        name = (character.get("name") or "").strip()
        if name:
            add(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))

        # base_slug nếu CSV có cột riêng
        add(character.get("base_slug") or "")
        add(character.get("char_slug") or "")

    parts = [p for p in (character_slug or "").split("-") if p]
    # progressive prefixes: a-b-c-d → a-b-c, a-b, a
    for n in range(len(parts) - 1, 0, -1):
        add("-".join(parts[:n]))

    # underscore variants (CSV đôi khi dùng _)
    for s in list(candidates):
        add(s.replace("-", "_"))

    return candidates


def load_character_epithets(character_slug, character=None):
    """Đọc epithets, gộp requirement theo title."""
    lookup = set(character_lookup_slugs(character_slug, character))
    rows = read_csv_file("character_epithets.csv")

    grouped = {}
    title_order = []

    for row in rows:
        if row.get("character_slug", "").strip() not in lookup:
            continue

        title = row.get("title", "").strip()
        if not title:
            continue

        if title not in grouped:
            grouped[title] = []
            title_order.append(title)

        requirement = row.get("requirement", "").strip()
        if requirement:
            grouped[title].append(requirement)

    return [
        {"title": title, "requirements": grouped[title]}
        for title in title_order
    ]


def get_character_unique_skills(character):
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
            "skill": skill,
        })

    return tiers


def get_character_innate_skills(character):
    return get_skills_by_ids(character.get("innate_skill_ids", ""))


def get_character_event_skills(character):
    return get_skills_by_ids(character.get("event_skill_ids", ""))


def get_character_awakenings(character):
    """Awakening skills level 2, 3, 4, 5."""
    items_by_id = load_items_by_id()
    awakenings = []

    for level in range(2, 6):
        prefix = f"awakening_lvl{level}_"
        skill_id = character.get(prefix + "skill_id", "").strip()
        skill = None

        if skill_id:
            matched = get_skills_by_ids(skill_id)
            if matched:
                skill = matched[0]
            else:
                skill = {
                    "id": skill_id,
                    "name": skill_id.replace("_", " ").title(),
                    "image": "",
                    "description": f"(Skill not found: {skill_id})",
                    "short_description": f"Missing: {skill_id}",
                    "category": "unknown",
                    "rarity": "",
                    "display_name": skill_id.replace("_", " ").title(),
                    "highlight": "no",
                    "_missing": True,
                }

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
                    "how_to_get": "",
                },
            )
            for item_id in item_ids
        ]

        if not skill_id and not items:
            continue

        # Level 3 và Level 5 luôn tô vàng (gold) như game / GameTora Global.
        # CSV highlight=yes vẫn được tôn trọng cho level khác.
        csv_highlight = character.get(prefix + "highlight", "").strip().lower() == "yes"
        force_gold = level in (3, 5)

        awakenings.append({
            "level": level,
            "skill": skill,
            "highlight": force_gold or csv_highlight,
            "materials": items,
        })

    return awakenings


def _resolve_race(slug, races_by_slug, all_races):
    slug = (slug or "").strip()
    if not slug:
        return "", {}

    candidates = [
        slug,
        slug.replace("-", "_"),
        slug.replace("_", "-"),
    ]

    if slug in RACE_SLUG_ALIASES:
        candidates.append(RACE_SLUG_ALIASES[slug])
    norm = slug.replace("-", "_")
    if norm in RACE_SLUG_ALIASES:
        candidates.append(RACE_SLUG_ALIASES[norm])

    for c in candidates:
        if c in races_by_slug and races_by_slug[c]:
            return c, races_by_slug[c]
        if c in all_races:
            return c, all_races[c]

    norm2 = slug.replace("-", "_")
    for s, race in all_races.items():
        if s == norm2:
            return s, race

    # Fuzzy: slug dài chứa / bị chứa bởi races.csv (vd nambu_hai ↔ m_c_nambu_hai)
    for s, race in all_races.items():
        if norm2 in s or s in norm2:
            if len(norm2) >= 6 and len(s) >= 6:
                return s, race

    return norm2, {}


def _parse_nolink_objective(race_slug, requirement):
    """
    Objective KHÔNG gắn 1 race cụ thể (không link race_detail):
      - Have at least N fans
      - Place 3rd or better in 2 G1 races
      - CSV cũ: race_slug trống + Place 3000th...
    Trả về (is_nolink, requirement_text).
    """
    req = (requirement or "").strip()
    slug = (race_slug or "").strip()

    if req.lower().startswith("have at least"):
        return True, req

    # CSV cũ fan: Place 3000th or better in (không có race)
    match = _FAN_PLACE_RE.match(req)
    if not slug and match:
        fans = int(match.group(1))
        if fans >= 100:
            return True, f"Have at least {fans} fans"

    if not slug and req:
        # Mọi objective không có race_slug: fans / G1 races / ...
        return True, req

    # Có race_slug nhưng text đã là full sentence grade objective
    low = req.lower()
    if re.search(r"\b\d+\s+g[123]\s+races?\b", low) or re.search(r"\bin\s+\d+\s+g[123]\b", low):
        return True, req

    return False, req


def get_character_objectives(character_slug, character=None):
    """
    Objectives từ character_objectives.csv.

    Fan goal: race_slug trống + requirement "Have at least N fans"
    (hoặc CSV cũ "Place 3000th or better in").
    KHÔNG bao giờ lọc bỏ dòng không có race_slug.
    """
    lookup = set(character_lookup_slugs(character_slug, character))
    # thêm chính slug trang đang xem
    lookup.add((character_slug or "").strip())
    lookup.add((character_slug or "").strip().replace("_", "-"))

    rows = []
    for row in read_csv_file("character_objectives.csv"):
        row_slug = (row.get("character_slug") or "").strip()
        if not row_slug:
            continue
        if (
            row_slug in lookup
            or row_slug.replace("_", "-") in lookup
            or row_slug.replace("-", "_") in lookup
        ):
            rows.append(row)

    # Dedup giữ thứ tự
    deduped = []
    seen = set()
    for row in rows:
        key = (
            (row.get("sort_order") or "").strip(),
            (row.get("race_slug") or "").strip(),
            (row.get("turn") or "").strip(),
            (row.get("requirement") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    rows = deduped

    def sort_key(row):
        try:
            return int((row.get("sort_order") or "0").strip() or 0)
        except ValueError:
            return 0

    rows.sort(key=sort_key)

    raw_slugs = [(row.get("race_slug") or "").strip() for row in rows if (row.get("race_slug") or "").strip()]
    races_by_slug = get_races_by_slugs(raw_slugs)
    all_races = {
        (r.get("slug") or "").strip(): r
        for r in load_races()
        if (r.get("slug") or "").strip()
    }

    objectives = []
    previous_turn = None

    for index, row in enumerate(rows, start=1):
        csv_race_slug = (row.get("race_slug") or "").strip()
        requirement = (row.get("requirement") or "").strip()
        is_nolink, requirement = _parse_nolink_objective(csv_race_slug, requirement)

        try:
            turn = int((row.get("turn") or "0").strip() or 0)
        except ValueError:
            turn = 0

        if previous_turn is None:
            turn_label = f"Turn {turn}"
        else:
            turn_label = f"Turn {turn} (previous + {turn - previous_turn})"
        previous_turn = turn

        if is_nolink:
            objectives.append({
                "index": index,
                "requirement": requirement,
                "race_slug": "",
                "race_name": "",
                "race_image": "fans.png",
                "is_fan_goal": True,   # template legacy
                "is_nolink_goal": True,
                "turn_label": turn_label,
                "class_label": "",
                "month_label": "",
                "info_line": "",
            })
            continue

        race_slug, race = _resolve_race(csv_race_slug, races_by_slug, all_races)

        half_key = (race.get("schedule_half") or "").strip().lower()
        half_label = SCHEDULE_HALF_LABELS.get(
            half_key,
            race.get("schedule_half") or "",
        )
        month_label = " ".join(
            part
            for part in [half_label, race.get("schedule_month") or ""]
            if part
        )

        distance_m = race.get("distance_m") or ""
        info_parts = [
            race.get("grade") or "",
            race.get("terrain") or "",
            (str(distance_m) + "m") if distance_m else "",
            race.get("distance_type") or "",
        ]
        info_line = " – ".join(part for part in info_parts if part)

        objectives.append({
            "index": index,
            "requirement": requirement,
            "race_slug": race_slug,
            "race_name": race.get("name")
            or race_slug.replace("_", " ").replace("-", " ").title(),
            "race_image": race.get("image") or "",
            "is_fan_goal": False,
            "is_nolink_goal": False,
            "turn_label": turn_label,
            "class_label": race.get("career_class") or "",
            "month_label": month_label,
            "info_line": info_line,
        })

    return objectives



def load_character_training_events(character_slug, character=None):
    """Đọc training events theo slug base hoặc costume."""
    lookup = set(character_lookup_slugs(character_slug, character))
    rows = read_csv_file("character_training_events.csv")

    grouped = {group_key: [] for group_key, _ in CHARACTER_TRAINING_EVENT_GROUPS}
    seen = set()

    for row in rows:
        row_slug = row.get("character_slug", "").strip()
        if row_slug not in lookup:
            continue
        group = (row.get("group") or "").strip()
        # Map tên group cũ (nếu crawl cũ dùng version/wchoice/...)
        group_aliases = {
            "version": "costume",
            "wchoice": "choices",
            "outings": "date",
            "nochoice": "no_choices",
            "no_choice": "no_choices",
        }
        group = group_aliases.get(group, group)
        if group not in grouped:
            # Không bỏ mất event lạ — gom vào no_choices
            group = "no_choices"
        event_id = (row.get("event_id") or "").strip()
        key = (group, event_id, (row.get("title") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        grouped[group].append(row)

    for group_key in grouped:
        def sort_key(r):
            try:
                return int(r.get("sort_order") or 0)
            except ValueError:
                return 0

        grouped[group_key].sort(key=sort_key)

    return grouped


def load_status_effects():
    """Đọc status_effects.csv → list dict + map name/slug → row."""
    rows = read_csv_file("status_effects.csv")
    effects = []
    by_name = {}
    by_slug = {}

    for row in rows:
        name = (row.get("name") or "").strip()
        slug = (row.get("slug") or "").strip()
        if not name:
            continue
        item = {
            "id": (row.get("id") or "").strip(),
            "slug": slug,
            "name": name,
            "type": (row.get("type") or "neutral").strip().lower() or "neutral",
            "description": (row.get("description") or "").strip(),
        }
        effects.append(item)
        by_name[name.lower()] = item
        # variants without ○/◎ spacing
        by_name[name.replace("○", "").replace("◎", "").strip().lower()] = item
        if slug:
            by_slug[slug] = item

    return effects, by_name, by_slug
