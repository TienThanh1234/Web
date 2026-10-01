"""Character Profile detail data (CSV)."""
from __future__ import annotations

from utils import read_csv_file

EXTRA_CATEGORIES = {"portrait", "comic", "support"}  # ẩn khi bỏ tick "More pictures" (gacha đã bỏ)
MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _s(row, *keys, default=""):
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return default


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def load_profiles_index():
    """List view: one row per profile."""
    out = []
    for r in read_csv_file("character_profiles.csv"):
        slug = _s(r, "slug")
        if not slug:
            continue
        out.append({
            "slug": slug,
            "char_id": _s(r, "char_id"),
            "name": _s(r, "name"),
            "image": _s(r, "face_image", "image") or "face.png",
            "version": "",
        })
    out.sort(key=lambda x: x["name"].lower())
    return out


def _build_tree(rows):
    """pedigree rows (path = sire / sire.dam / ...) -> cây lồng nhau."""
    by_path = {r["path"]: r for r in rows if r["path"]}

    def node(path):
        r = by_path.get(path)
        if not r:
            return None
        kids = [k for k in (node(path + ".sire"), node(path + ".dam")) if k]
        return {
            "name": r["name"],
            "sex": "sire" if r["path"].split(".")[-1] == "sire" else "dam",
            "char_slug": r["char_slug"],
            "children": kids,
        }

    return [n for n in (node("sire"), node("dam")) if n]


def get_profile(slug: str) -> dict | None:
    slug = (slug or "").strip()
    if not slug:
        return None

    base = next((r for r in read_csv_file("character_profiles.csv") if _s(r, "slug") == slug), None)
    if base is None:
        return None

    secrets = [
        _s(r, "text")
        for r in read_csv_file("character_profile_secrets.csv")
        if _s(r, "slug") == slug and _s(r, "text")
    ]

    char_id = _s(base, "char_id")
    gallery = []
    for r in read_csv_file("character_profile_gallery.csv"):
        if _s(r, "slug") != slug:
            continue
        cat = (_s(r, "category") or "other").lower()
        label = _s(r, "label")
        # Bỏ Gacha preview (chưa có data / không dùng)
        if cat == "gacha" or label.lower().startswith("gacha preview"):
            continue

        raw_file = _s(r, "file") or _s(r, "thumb")
        raw_file = raw_file.replace("\\", "/").replace("thumb/", "").lstrip("/")
        raw_thumb = _s(r, "thumb") or raw_file
        raw_thumb = raw_thumb.replace("\\", "/").replace("thumb/", "").lstrip("/") or raw_file

        # Fallback tên file portrait (folder có cả portrait_1.png lẫn portrait_profile_ID_000001.png)
        alts = []
        if cat == "portrait" and raw_file.startswith("portrait_") and "trainee" not in raw_file:
            stem = raw_file[len("portrait_"):]
            if stem.endswith(".png"):
                stem = stem[:-4]
            if stem.isdigit() and char_id:
                n = int(stem)
                alts = [
                    f"portrait_profile_{char_id}_{n:06d}.png",
                    f"portrait_profile_{char_id}_{n}.png",
                    f"portrait_{n}.png",
                ]
                # ưu tiên file CSV trước, rồi alt
                alts = [raw_file] + [a for a in alts if a != raw_file]
        if cat == "portrait" and raw_file.startswith("portrait_profile_") and char_id:
            # portrait_profile_1051_000001.png -> portrait_1.png
            parts = raw_file.replace(".png", "").split("_")
            if parts and parts[-1].isdigit():
                n = int(parts[-1])
                alts = [raw_file, f"portrait_{n}.png"]

        gallery.append({
            "sort_order": _int(_s(r, "sort_order")),
            "label": label,
            "category": cat,
            "extra": cat in EXTRA_CATEGORIES,
            "media_type": _s(r, "media_type") or "image",
            "file": raw_file,
            "thumb": raw_thumb or raw_file,
            "alts": alts,  # template onerror chain
            "video": _s(r, "video"),
        })
    gallery.sort(key=lambda x: x["sort_order"])

    rl = None
    for r in read_csv_file("character_profile_rl.csv"):
        if _s(r, "slug") == slug:
            earnings = [e.strip() for e in _s(r, "earnings").split("|") if e.strip()]
            earnings = [f"{e} JPY" if e.isdigit() else e for e in earnings]
            rl = {
                "country": _s(r, "country").lower(),
                "races": _s(r, "races"),
                "wins": _s(r, "wins"),
                "record": _s(r, "record"),
                "earnings": earnings,
                "date_of_birth": _s(r, "date_of_birth"),
                "date_of_death": _s(r, "date_of_death") or "Alive",
                "siblings": _s(r, "siblings"),
                "offspring": _s(r, "offspring"),
            }
            break

    pedigree_rows = [
        {
            "gen": _int(_s(r, "gen")),
            "path": _s(r, "path"),
            "name": _s(r, "name"),
            "sex": _s(r, "sex"),
            "char_slug": _s(r, "char_slug"),
        }
        for r in read_csv_file("character_profile_pedigree.csv")
        if _s(r, "slug") == slug
    ]

    race_history = []
    for r in read_csv_file("character_profile_race_history.csv"):
        if _s(r, "slug") != slug:
            continue
        place = _s(r, "place")
        race_history.append({
            "sort_order": _int(_s(r, "sort_order")),
            "place": place,
            "place_label": _s(r, "place_label"),
            "race_name": _s(r, "race_name"),
            "date": _s(r, "date"),
            "winner": _s(r, "winner"),
            "winner_slug": _s(r, "winner_slug"),
            "track": _s(r, "track"),
            "surface": _s(r, "surface"),
            "distance": _s(r, "distance"),
            "grade": _s(r, "grade"),
            "netkeiba_url": _s(r, "netkeiba_url"),
            "jbis_url": _s(r, "jbis_url"),
        })
    race_history.sort(key=lambda x: x["sort_order"])

    bm, bd = _int(_s(base, "birth_month")), _int(_s(base, "birth_day"))
    birthday = _s(base, "birthday") or (f"{MONTHS[bm]} {bd}" if 0 < bm <= 12 and bd else "")

    return {
        "slug": slug,
        "char_id": _s(base, "char_id"),
        "name": _s(base, "name"),
        "name_ja": _s(base, "name_ja"),
        "tagline": _s(base, "tagline"),
        "self_intro": _s(base, "self_intro"),
        "voice_actor": _s(base, "voice_actor"),
        "voice_actor_link": _s(base, "voice_actor_link"),
        "birthday": birthday,
        "school": _s(base, "school", "class"),
        "dorm": _s(base, "dorm"),
        "color_main": (_s(base, "color_main") or "888888").lstrip("#"),
        "color_sub": (_s(base, "color_sub") or "cccccc").lstrip("#"),
        "height": _s(base, "height"),
        "weight": _s(base, "weight"),
        "three_sizes": _s(base, "three_sizes"),
        "shoe_size": _s(base, "shoe_size"),
        "strong": _s(base, "strong"),
        "weak": _s(base, "weak"),
        "ears": _s(base, "ears"),
        "tail": _s(base, "tail"),
        "family": _s(base, "family"),
        "main_image": _s(base, "main_image") or "idle.png",
        "face_image": _s(base, "face_image") or "face.png",
        "hero_video": _s(base, "hero_video"),
        "secrets": secrets,
        "gallery": gallery,
        "has_extra_gallery": any(g["extra"] for g in gallery),
        "rl": rl,
        "pedigree": pedigree_rows,
        "pedigree_tree": _build_tree(pedigree_rows),
        "race_history": race_history,
    }