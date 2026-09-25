"""Gacha banners — CSV trong data/ + map link sang character/support local."""
from collections import defaultdict
from datetime import datetime
import re

from utils import read_csv_file


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _norm(text):
    s = (text or "").strip().lower()
    s = s.replace("☆", " ").replace("★", " ").replace("!", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _slugify(text):
    s = _norm(text)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _build_character_link_index():
    """
    Map rate-up → slug trong characters local.
    Trả về: by_card_id, by_name_version, by_name
    Ưu tiên resolve: card_id > name+version > name.
    """
    try:
        from services.character_service import load_characters
        characters = load_characters()
    except Exception as exc:
        print(f"[gacha] load_characters lỗi: {exc}")
        return {}, {}, {}

    by_card_id = {}
    by_name_version = {}
    by_name = {}

    for c in characters:
        slug = (c.get("slug") or "").strip()
        name = (c.get("name") or "").strip()
        version = (c.get("version") or "").strip()
        card_id = str(c.get("card_id") or "").strip()
        if not slug or not name:
            continue

        if card_id:
            by_card_id[card_id] = slug

        name_n = _norm(name)
        version_n = _norm(version)
        by_name_version[(name_n, version_n)] = slug
        # biến thể: bỏ ký tự đặc biệt trong version
        by_name_version[(name_n, _slugify(version).replace("-", " "))] = slug
        by_name_version[(name_n, _slugify(version))] = slug
        # chỉ theo tên — lấy bản mới nhất (cuối list) nếu trùng
        by_name[name_n] = slug

    return by_card_id, by_name_version, by_name


def _build_support_link_index():
    """
    Map rate-up → id support_cards local (dùng cho support_detail).
    """
    try:
        from services.support_service import load_support_cards
        cards = load_support_cards()
    except Exception as exc:
        print(f"[gacha] load_support_cards lỗi: {exc}")
        return {}, {}, {}

    by_id = {}
    by_name_title = {}
    by_name = {}

    for c in cards:
        cid = str(c.get("id") or "").strip()
        name = (c.get("name") or "").strip()
        title = (c.get("title") or "").strip().strip("[] ")
        rarity = (c.get("rarity") or "").strip()
        stype = (c.get("type") or "").strip()
        if not cid:
            continue
        by_id[cid] = cid
        if name:
            by_name.setdefault(_norm(name), cid)
            by_name_title[(_norm(name), _norm(title))] = cid
            # detail crawler: "SSR Power" / "SR Speed"
            detail_a = _norm(f"{rarity} {stype}")
            detail_b = _norm(f"{stype}")
            if detail_a:
                by_name_title[(_norm(name), detail_a)] = cid
            if detail_b:
                by_name_title[(_norm(name), detail_b)] = cid

    return by_id, by_name_title, by_name


def _resolve_character_slug(name, detail, link_slug, card_id, char_card, char_nv, char_name):
    """
    Resolve character rate-up → local slug.
    Ưu tiên: card_id (chính xác) > name+detail > link_slug > name only.
    """
    # 1) card_id từ rateups.csv khớp characters.card_id
    cid = str(card_id or "").strip()
    if cid and cid in char_card:
        return char_card[cid]

    name_n = _norm(name)
    detail_n = _norm(detail)

    # 2) name + costume/version (detail từ rateup)
    if name_n and detail_n:
        if (name_n, detail_n) in char_nv:
            return char_nv[(name_n, detail_n)]
        detail_slug = _slugify(detail)
        if (name_n, detail_slug) in char_nv:
            return char_nv[(name_n, detail_slug)]
        if (name_n, detail_slug.replace("-", " ")) in char_nv:
            return char_nv[(name_n, detail_slug.replace("-", " "))]
        # fuzzy: detail nằm trong version hoặc ngược lại
        for (n, v), slug in char_nv.items():
            if n != name_n or not v:
                continue
            if detail_n in v or v in detail_n:
                return slug
            if _slugify(detail_n) == _slugify(v):
                return slug
            # "buono alla moda" vs "bono alla moda"
            d_tokens = set(detail_slug.split("-"))
            v_tokens = set(_slugify(v).split("-"))
            if d_tokens and v_tokens and len(d_tokens & v_tokens) >= max(1, len(d_tokens) - 1):
                return slug

    # 3) link_slug crawler (base name hoặc full)
    if link_slug:
        ls = link_slug.strip()
        for slug in set(list(char_nv.values()) + list(char_name.values())):
            if slug == ls or _slugify(slug) == _slugify(ls):
                return slug

    # 4) chỉ theo tên (fallback — có thể sai costume)
    if name_n in char_name:
        return char_name[name_n]

    return ""


def _resolve_support_id(name, detail, link_slug, card_id, by_id, by_nt, by_name):
    # 1) id crawler / card_id có trong DB
    for cand in (str(link_slug or "").strip(), str(card_id or "").strip()):
        if cand and cand in by_id:
            return cand

    name_n = _norm(name)
    detail_n = _norm(detail)

    # 2) name + title/rarity type
    if name_n and detail_n and (name_n, detail_n) in by_nt:
        return by_nt[(name_n, detail_n)]

    if name_n and detail_n:
        for (n, t), cid in by_nt.items():
            if n != name_n:
                continue
            if not t:
                continue
            if detail_n in t or t in detail_n:
                return cid
            # "ssr power" vs "power"
            if all(tok in t for tok in detail_n.split() if len(tok) > 2):
                return cid

    # 3) chỉ tên
    if name_n in by_name:
        return by_name[name_n]

    return ""


def load_rateups_by_banner():
    char_card, char_nv, char_name = _build_character_link_index()
    sup_id, sup_nt, sup_name = _build_support_link_index()

    grouped = defaultdict(list)
    for row in read_csv_file("gacha_rateups.csv"):
        banner_id = (row.get("banner_id") or "").strip()
        if not banner_id:
            continue

        name = (row.get("name") or "").strip()
        detail = (row.get("detail") or "").strip()
        link_type = (row.get("link_type") or "").strip().lower()
        link_slug = (row.get("link_slug") or "").strip()
        card_id = (row.get("card_id") or "").strip()

        resolved = ""
        if link_type == "character":
            resolved = _resolve_character_slug(
                name, detail, link_slug, card_id, char_card, char_nv, char_name
            )
        elif link_type == "support":
            resolved = _resolve_support_id(
                name, detail, link_slug, card_id, sup_id, sup_nt, sup_name
            )

        grouped[banner_id].append({
            "name": name,
            "detail": detail,
            "rate_pct": (row.get("rate_pct") or "").strip(),
            "status": (row.get("status") or "").strip(),
            "link_type": link_type,
            "link_slug": resolved or "",
            "card_id": card_id,
            "sort_order": _int(row.get("sort_order"), 0),
            # chỉ hiện link khi resolve được
            "has_link": bool(resolved),
        })

    for items in grouped.values():
        items.sort(key=lambda x: x["sort_order"])
    return grouped


def load_banners():
    rateups = load_rateups_by_banner()
    banners = []
    for row in read_csv_file("gacha_banners.csv"):
        banner_id = (row.get("id") or "").strip()
        if not banner_id:
            continue
        banners.append({
            "id": banner_id,
            "server": (row.get("server") or "global").strip().lower(),
            "year": _int(row.get("year")),
            "banner_type": (row.get("banner_type") or "").strip().lower(),
            "title": (row.get("title") or "").strip(),
            "image": (row.get("image") or "").strip(),
            "start_at": (row.get("start_at") or "").strip(),
            "end_at": (row.get("end_at") or "").strip(),
            "is_current": (row.get("is_current") or "").strip() in ("1", "true", "True", "yes"),
            "is_special": (row.get("is_special") or "").strip() in ("1", "true", "True", "yes"),
            "sort_order": _int(row.get("sort_order"), 0),
            "rateups": rateups.get(banner_id, []),
        })
    banners.sort(key=lambda b: b["sort_order"], reverse=True)
    return banners


def get_current_banners():
    return [b for b in load_banners() if b["is_current"] and not b["is_special"]]


def get_special_banners():
    return [b for b in load_banners() if b["is_special"]]


def get_history_index():
    years_types = set()
    for b in load_banners():
        if b["is_special"]:
            continue
        if b["year"] and b["banner_type"] in ("character", "support"):
            years_types.add((b["year"], b["banner_type"]))
    for y in (2025, 2026):
        for t in ("character", "support"):
            years_types.add((y, t))
    items = sorted(years_types, key=lambda x: (x[0], 0 if x[1] == "character" else 1))
    return [
        {
            "year": year,
            "banner_type": btype,
            "label": f"{year} ({'characters' if btype == 'character' else 'support cards'})",
        }
        for year, btype in items
    ]


def filter_banners(year=None, banner_type=None, server="global"):
    yt = None if year in (None, "", "all", "All") else _int(year)
    bt = (banner_type or "all").strip().lower()
    if bt in ("characters", "char"):
        bt = "character"
    if bt in ("supports", "support cards", "sup"):
        bt = "support"
    if bt == "all":
        bt = None

    result = []
    for b in load_banners():
        if b["is_special"]:
            continue
        if server and b.get("server", "global") not in (server, "global", ""):
            continue
        if yt and b["year"] != yt:
            continue
        if bt and b["banner_type"] != bt:
            continue
        result.append(b)
    result.sort(key=lambda b: b["start_at"], reverse=True)
    return result


def get_banners_for_history(year, banner_type):
    return filter_banners(year=year, banner_type=banner_type, server="global")


def format_banner_period(banner):
    start = banner.get("start_at") or ""
    end = banner.get("end_at") or ""

    def short(s):
        if not s or len(s) < 10:
            return s
        try:
            dt = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
            month = dt.strftime("%b")
            if month == "Sep":
                month = "Sept"
            return f"{dt.day} {month} {dt.year}"
        except ValueError:
            return s

    if start and end:
        return f"{short(start)} – {short(end)}"
    return start or end
