"""Scenario detail guides from CSV.

URA  → data/ura_finale_data.csv  (giữ file cũ của bạn)
Unity → data/Unity.csv
List  → scenarios.csv + scenario_linked_characters.csv (scenario_service)
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from flask import url_for

from config import BASE_DIR

DATA_DIR = Path(BASE_DIR) / "data"

GUIDE_FILES = {
    "ura-finals": "ura_finale_data.csv",
    "unity-cup": "Unity.csv",
    "trackblazer": "Trackblazer.csv",
    "our-grand-concert": "GrandLive.csv",
}

GUIDE_META = {
    "ura-finals": {
        "slug": "ura-finals",
        "title": "URA Finale Scenario",
        "authors": "Thanh Umamusume",
        "last_updated": "2026-09-29",
        "image_folder": "ura_finale",
    },
    "unity-cup": {
        "slug": "unity-cup",
        "title": "Unity Cup Scenario",
        "authors": "Thanh Umamusume",
        "last_updated": "2026-09-29",
        "image_folder": "unity",
    },
    "trackblazer": {
        "slug": "trackblazer",
        "title": "Trackblazer Scenario",
        "authors": "Thanh Umamusume",
        "last_updated": "2026-09-29",
        "image_folder": "Trackblazer",
    },
    "our-grand-concert": {
        "slug": "our-grand-concert",
        "title": "Our Grand Concert (Grand Live) Scenario",
        "authors": "Thanh Umamusume",
        "last_updated": "2026-09-30",
        "image_folder": "GrandLive",
    },
}

LINK_RE = re.compile(r"\[\[(skill|char):([a-z0-9_]+)\|([^\]]+)\]\]", re.I)
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _read_csv(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_guide_meta(slug: str) -> dict | None:
    meta = GUIDE_META.get(slug)
    if not meta:
        return None
    return dict(meta)


def linkify_text(text: str, skill_ids: dict, char_slugs: dict) -> str:
    if not text:
        return ""

    def repl(m):
        kind, key, label = m.group(1).lower(), m.group(2), m.group(3)
        if kind == "skill":
            sid = (skill_ids or {}).get(key, "")
            if not sid:
                # fallback: key often matches Supabase skill id (text_to_id name)
                sid = key
            try:
                return f'<a class="guide-link" href="{url_for("skill_detail", skill_id=sid)}">{label}</a>'
            except Exception:
                return f'<span class="guide-link">{label}</span>'
        slug = (char_slugs or {}).get(key, "")
        if slug:
            try:
                return f'<a class="guide-link" href="{url_for("character_detail", slug=slug)}">{label}</a>'
            except Exception:
                pass
        return f'<span class="guide-link">{label}</span>'

    out = LINK_RE.sub(repl, text)
    out = BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = ITALIC_RE.sub(r"<em>\1</em>", out)
    return out


def _split_table_cells(line: str) -> list[str]:
    """Split by | but keep [[skill:id|Label]] / [[char:slug|Name]] intact."""
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    depth = 0
    s = line or ""
    n = len(s)
    while i < n:
        if s.startswith("[[", i):
            depth += 1
            buf.append("[[")
            i += 2
            continue
        if s.startswith("]]", i) and depth > 0:
            depth -= 1
            buf.append("]]")
            i += 2
            continue
        if s[i] == "|" and depth == 0:
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(s[i])
        i += 1
    cells.append("".join(buf).strip())
    return cells


def parse_table(headers: str, rows_text: str) -> dict:
    hdrs = _split_table_cells(headers) if headers else []
    body = []
    for part in (rows_text or "").split(";;"):
        part = part.strip()
        if part:
            body.append(_split_table_cells(part))
    return {"headers": hdrs, "rows": body}


def _nest_list_items(flat: list[dict]) -> list[dict]:
    roots = []
    current = None
    for it in flat:
        nest = int(it.get("nest") or 0)
        node = {"html": it["html"], "children": []}
        if nest == 0:
            roots.append(node)
            current = node
        else:
            if current is not None:
                current["children"].append(node)
            else:
                roots.append(node)
                current = node
    return roots


def _normalize_ura_rows(raw: list[dict]) -> list[dict]:
    """ura_finale_data.csv có thể dùng cột section/content kiểu cũ → chuẩn hóa."""
    out = []
    for i, row in enumerate(raw, start=1):
        # format mới (giống Unity)
        if row.get("block_type"):
            r = dict(row)
            r.setdefault("sort_order", str(i))
            out.append(r)
            continue
        # format cũ: section, content, type, image...
        section = (row.get("section") or row.get("Section") or "").strip()
        content = (row.get("content") or row.get("text") or row.get("detail") or "").strip()
        btype = (row.get("type") or row.get("block_type") or "paragraph").strip().lower()
        image = (row.get("image") or "").strip()
        heading = (row.get("heading") or row.get("title") or "").strip()

        if section and not heading and btype in ("heading", "section", ""):
            # first row of section as heading
            out.append({
                "sort_order": str(i),
                "block_type": "heading",
                "heading_id": section.lower().replace(" ", "-"),
                "heading": section,
                "text": "",
                "image": "",
                "image_max": "",
                "table_headers": "",
                "table_rows": "",
                "nest_level": "",
            })
        if image:
            out.append({
                "sort_order": str(i),
                "block_type": "image",
                "heading_id": "",
                "heading": "",
                "text": "",
                "image": image,
                "image_max": "100%",
                "table_headers": "",
                "table_rows": "",
                "nest_level": "",
            })
        if content:
            out.append({
                "sort_order": str(i),
                "block_type": btype if btype in (
                    "paragraph", "list_item", "note", "intro", "table"
                ) else "paragraph",
                "heading_id": "",
                "heading": heading,
                "text": content,
                "image": "",
                "image_max": "",
                "table_headers": row.get("table_headers", ""),
                "table_rows": row.get("table_rows", ""),
                "nest_level": row.get("nest_level", ""),
            })
    return out


def load_raw_blocks(slug: str) -> list[dict]:
    fname = GUIDE_FILES.get(slug)
    if not fname:
        return []
    raw = _read_csv(fname)
    if slug == "ura-finals":
        # nếu đã là format Unity thì dùng thẳng
        if raw and raw[0].get("block_type"):
            return raw
        return _normalize_ura_rows(raw)
    return raw


def prepare_blocks(raw: list[dict], skill_ids: dict, char_slugs: dict) -> list[dict]:
    prepared = []
    list_buf = []

    def flush():
        nonlocal list_buf
        if list_buf:
            prepared.append({"block_type": "list", "list_items": _nest_list_items(list_buf)})
            list_buf = []

    def order_key(r):
        try:
            return int(str(r.get("sort_order") or "0").strip() or 0)
        except ValueError:
            return 0

    for b in sorted(raw, key=order_key):
        bt = (b.get("block_type") or "").strip()
        if bt in ("list_item", "list_item_nested"):
            nest = int((b.get("nest_level") or "0") or 0)
            if bt == "list_item_nested" and nest == 0:
                nest = 1
            list_buf.append({
                "html": linkify_text(b.get("text") or "", skill_ids, char_slugs),
                "nest": nest,
            })
            continue
        flush()
        item = {
            "block_type": bt,
            "heading_id": (b.get("heading_id") or "").strip(),
            "heading": (b.get("heading") or "").strip(),
            "image": (b.get("image") or "").strip(),
            "image_max": (b.get("image_max") or "100%").strip() or "100%",
            "html": linkify_text(b.get("text") or "", skill_ids, char_slugs),
            "table": None,
        }
        if bt == "table":
            tbl = parse_table(b.get("table_headers") or "", b.get("table_rows") or "")
            tbl["headers"] = [linkify_text(h, skill_ids, char_slugs) for h in tbl["headers"]]
            tbl["rows"] = [[linkify_text(c, skill_ids, char_slugs) for c in row] for row in tbl["rows"]]
            item["table"] = tbl

        if bt == "skill_item":
            # heading_id holds skill key, heading = name, text = description, image = icon
            key = (b.get("heading_id") or "").strip()
            name = (b.get("heading") or "").strip()
            desc = linkify_text(b.get("text") or "", skill_ids, char_slugs)
            icon = (b.get("image") or "").strip()
            sid = (skill_ids or {}).get(key, "")
            href = ""
            if sid:
                try:
                    href = url_for("skill_detail", skill_id=sid)
                except Exception:
                    href = ""
            item["skill"] = {
                "key": key,
                "name": name,
                "desc": desc,
                "icon": icon,
                "href": href,
                "skill_id": sid,
            }
        prepared.append(item)
    flush()
    return prepared


def build_toc(raw: list[dict]) -> list[dict]:
    toc = []
    for b in sorted(raw, key=lambda r: int(str(r.get("sort_order") or 0) or 0)):
        bt = (b.get("block_type") or "").strip()
        if bt not in ("heading", "subheading"):
            continue
        toc.append({
            "id": (b.get("heading_id") or "").strip(),
            "title": (b.get("heading") or "").strip(),
            "level": 1 if bt == "heading" else 2,
        })
    return toc


def get_scenario_guide(slug: str, skill_ids=None, char_slugs=None):
    meta = load_guide_meta(slug)
    if not meta:
        return None
    raw = load_raw_blocks(slug)
    skill_ids = skill_ids or {}
    char_slugs = char_slugs or {}
    return {
        "meta": meta,
        "toc": build_toc(raw),
        "blocks": prepare_blocks(raw, skill_ids, char_slugs),
        "raw_count": len(raw),
    }
