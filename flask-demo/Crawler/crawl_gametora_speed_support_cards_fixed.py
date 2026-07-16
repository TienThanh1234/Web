"""
Crawler support cards GameTora Uma Musume và xuất ra đúng 3 file CSV của project Flask:

1) support_cards.csv
2) support_card_effects.csv
3) support_card_training_events.csv

Điểm quan trọng của bản này:
- Có manual filter mode: script mở browser, bạn tự lọc Speed/Stamina/Power/Guts... trên GameTora,
  sau đó quay lại terminal bấm Enter, script mới lấy danh sách card đang hiển thị.
- collect_support_links chỉ lấy link đang visible, tránh lấy cả card bị ẩn bởi filter.
- BẢN NÀY CLICK THẬT vào từng card đang hiện trên list, đọc detail, rồi Back về list để click card tiếp theo.
- Có --support-type để dùng lại cho speed/stamina/power/guts/wit sau này.

Cài lần đầu:
    pip install playwright requests
    python -m playwright install chromium

Crawl Speed theo cách bạn đang làm thủ công trên GameTora:
    python crawl_gametora_support_cards_click_each_card.py --manual-filter --support-type speed --limit 3

Sau khi test ổn, crawl toàn bộ Speed:
    python crawl_gametora_support_cards_click_each_card.py --manual-filter --support-type speed

Gộp vào 3 file CSV gốc:
    python crawl_gametora_support_cards_visible_only_fixed_v10.py --manual-filter --support-type speed --append

Sau này crawl Stamina/Power/Guts/Wit thì chỉ đổi --support-type:
    python crawl_gametora_support_cards_click_each_card.py --manual-filter --support-type stamina
    python crawl_gametora_support_cards_click_each_card.py --manual-filter --support-type power
    python crawl_gametora_support_cards_click_each_card.py --manual-filter --support-type guts
    python crawl_gametora_support_cards_click_each_card.py --manual-filter --support-type wit
"""

import argparse
import csv
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    requests = None

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


BASE_URL = "https://gametora.com"
DEFAULT_START_URL = "https://gametora.com/umamusume/supports"
OUTPUT_DIR = Path("crawl_output")

CARD_CSV = Path("support_cards.csv")
EFFECT_CSV = Path("support_card_effects.csv")
EVENT_CSV = Path("support_card_training_events.csv")
SKILL_CSV = Path("skills.csv")

IMAGE_DIR = Path("static/images/support_cards")

# Bạn đã tự viết xong Taiki Shuttle Speed rồi nên skip cứng luôn.
SKIP_CARD_IDS = {"taiki_shuttle"}
SKIP_CARD_NAMES = {"taiki shuttle"}

CARD_HEADERS = [
    "id",
    "name",
    "title",
    "image",
    "thumb_image",
    "rarity",
    "type",
    "release_date",
    "unique_effect",
    "hint_skill_ids",
    "event_skill_ids",
    "highlight_skill_ids",
    "stat_gain",
    "stat_icon",
]

EFFECT_HEADERS = [
    "card_id",
    "effect_name",
    "lb0",
    "lb1",
    "lb2",
    "lb3",
    "lb4",
]

EVENT_HEADERS = [
    "card_id",
    "section",
    "event_id",
    "title",
    "detail",
    "sort_order",
]

# Cột trong support_card_effects.csv vẫn giữ lb0 → lb4.
# Level thật phụ thuộc rarity:
# - SSR: Lv.30, 35, 40, 45, 50
# - SR : Lv.25, 30, 35, 40, 45
# - R  : Lv.20, 25, 30, 35, 40
EFFECT_COLUMNS = ["lb0", "lb1", "lb2", "lb3", "lb4"]


def get_effect_level_targets_by_rarity(rarity):
    rarity = clean_text(rarity).upper()

    if rarity == "SR":
        return [25, 30, 35, 40, 45]

    if rarity == "R":
        return [20, 25, 30, 35, 40]

    # Mặc định SSR. Nếu không đọc được rarity thì dùng SSR để tránh làm lệch dữ liệu card SSR.
    return [30, 35, 40, 45, 50]

SUPPORT_TYPES = [
    "speed",
    "stamina",
    "power",
    "guts",
    "wit",
    "intelligence",
    "friend",
    "group",
]


SUPPORT_TYPE_LABELS = {
    "speed": "Speed",
    "stamina": "Stamina",
    "power": "Power",
    "guts": "Guts",
    "wit": "Wit",
    "intelligence": "Wit",
    "friend": "Friend",
    "group": "Group",
    "all": "",
}


def normalize_support_type(value):
    value = clean_text(value).lower()

    if value == "intelligence":
        return "wit"

    if value in SUPPORT_TYPE_LABELS:
        return value

    return value


def display_support_type(value):
    value = normalize_support_type(value)
    return SUPPORT_TYPE_LABELS.get(value, value.title())

# Các tên effect thường gặp trên GameTora.
# Sort theo độ dài giảm dần để tránh match nhầm.
SUPPORT_EFFECT_NAMES = sorted(
    [
        "Friendship Bonus",
        "Mood Effect",
        "Training Effectiveness",
        "Initial Friendship Gauge",
        "Race Bonus",
        "Fan Bonus",
        "Hint Levels",
        "Hint Frequency",
        "Specialty Priority",
        "Speed Bonus",
        "Stamina Bonus",
        "Power Bonus",
        "Guts Bonus",
        "Wit Bonus",
        "Skill Point Bonus",
        "Event Recovery Amount",
        "Event Effectiveness",
        "Failure Rate Down",
        "Energy Discount",
        "Initial Speed",
        "Initial Stamina",
        "Initial Power",
        "Initial Guts",
        "Initial Wit",
        "Initial Skill Points",
        "Wisdom Friendship Recovery",
    ],
    key=len,
    reverse=True,
)

SECTION_STOP_TITLES = {
    "support_hints": [
        "Stat gain",
        "Skills from events",
        "Training Events",
        "Character Rate Up",
        "Support Rate Up",
        "Newest Scenario",
    ],
    "event_skills": [
        "Training Events",
        "Character Rate Up",
        "Support Rate Up",
        "Newest Scenario",
    ],
    "stat_gain": [
        "Skills from events",
        "Training Events",
        "Character Rate Up",
        "Support Rate Up",
        "Newest Scenario",
    ],
}


# =========================
# BASIC HELPERS
# =========================


def clean_text(text):
    if text is None:
        return ""

    text = str(text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def clean_line(text):
    text = clean_text(text)
    text = text.replace("❯", "›")
    text = text.replace("▶", "›")
    return text.strip()


def split_lines(text):
    lines = []

    for raw_line in clean_text(text).splitlines():
        line = clean_line(raw_line)

        if line:
            lines.append(line)

    return lines


def text_to_id(text):
    text = clean_text(text).lower()
    text = text.replace("◎", "oo")
    text = text.replace("○", "o")
    text = text.replace("×", "x")
    text = text.replace("☆", "")
    text = text.replace("★", "")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text




def skill_id_from_skill_url(href):
    """
    GameTora skill URL thường có dạng:
    /umamusume/skills/200041-firm-conditions-o
    -> firm_conditions_o
    """
    href = clean_text(href)

    if not href:
        return ""

    slug = urlparse(href).path.rstrip("/").split("/")[-1]
    slug = re.sub(r"^\d+-", "", slug)
    return text_to_id(slug)


def normalize_skill_lookup_key(text):
    text = clean_line(text)
    text = re.sub(r"\s+hint\s*\+?\d+\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+details\s*$", "", text, flags=re.IGNORECASE)
    text = text.replace("◎", "oo")
    text = text.replace("○", "o")
    text = text.replace("×", "x")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


_SKILL_LOOKUP_CACHE = None
_SKILL_ID_SET_CACHE = None


def load_skill_lookup_from_csv():
    """
    Đọc skills.csv để map tên skill GameTora -> id trong web.
    Nhờ vậy nếu GameTora không gắn link skill rõ ràng thì crawler vẫn lấy được skill_id từ text.
    """
    global _SKILL_LOOKUP_CACHE, _SKILL_ID_SET_CACHE

    if _SKILL_LOOKUP_CACHE is not None and _SKILL_ID_SET_CACHE is not None:
        return _SKILL_LOOKUP_CACHE, _SKILL_ID_SET_CACHE

    lookup = {}
    skill_ids = set()

    if SKILL_CSV.exists():
        with SKILL_CSV.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            for row in reader:
                skill_id = clean_text(row.get("id", ""))

                if not skill_id:
                    continue

                skill_ids.add(skill_id)

                candidates = [
                    row.get("name", ""),
                    row.get("display_name", ""),
                    skill_id.replace("_", " "),
                ]

                for candidate in candidates:
                    candidate = clean_text(candidate)

                    if not candidate:
                        continue

                    keys = {
                        normalize_skill_lookup_key(candidate),
                        text_to_id(candidate),
                    }

                    for key in keys:
                        if key:
                            lookup[key] = skill_id

    _SKILL_LOOKUP_CACHE = lookup
    _SKILL_ID_SET_CACHE = skill_ids
    return lookup, skill_ids


def skill_id_from_visible_text(text):
    text = clean_line(text)

    if not text:
        return ""

    ignored = {
        "Details",
        "More",
        "Support hints",
        "Skills from events",
        "Stat gain",
        "Training Events",
    }

    if text in ignored:
        return ""

    # Mô tả skill thường rất dài, tên skill ngắn hơn nhiều.
    if len(text) > 90:
        return ""

    # Loại bớt các dòng mô tả thường gặp.
    if re.search(r"\b(increase|decrease|when|upon|during|positioned|race|velocity|acceleration|fatigue|performance)\b", text, re.IGNORECASE):
        return ""

    lookup, skill_ids = load_skill_lookup_from_csv()
    direct_id = text_to_id(text)

    if direct_id in skill_ids:
        return direct_id

    key = normalize_skill_lookup_key(text)

    if key in lookup:
        return lookup[key]

    id_key = text_to_id(key)

    if id_key in lookup:
        return lookup[id_key]

    return ""


def normalize_effect_value(value):
    value = clean_text(value)

    if re.match(r"^Unlocked\s+at\s+level\s+\d+", value, re.IGNORECASE):
        return "0"

    if value.lower() in ["locked", "none", "-"]:
        return "0"

    return value

def slug_from_support_url(url):
    path = urlparse(url).path.rstrip("/")
    last = path.split("/")[-1]
    # 30026-twin-turbo -> twin-turbo
    last = re.sub(r"^\d+-", "", last)
    return last


def support_id_from_url(url, fallback_name=""):
    slug = slug_from_support_url(url)

    if slug:
        return text_to_id(slug)

    return text_to_id(fallback_name)


def make_unique_card_id(url, name, rarity, support_type, existing_ids=None, used_ids=None):
    """
    Tạo id không bị đụng giữa các loại support khác nhau.

    Vấn đề bản cũ:
    - Speed có silence_suzuka rồi.
    - Sang Stamina, GameTora vẫn có thể có slug silence-suzuka.
    - Nếu dùng lại id silence_suzuka thì crawler sẽ skip hoặc append không vào được.

    Quy ước bản này:
    - Speed SSR giữ id gọn: silence_suzuka
    - Speed SR/R thêm rarity: eishin_flash_sr, narita_top_road_r
    - Stamina/Power/Guts/Wit thêm type để không đụng Speed:
      silence_suzuka_stamina, eishin_flash_sr_stamina, ...
    - Nếu vẫn trùng thì thêm số GameTora ở cuối.
    """
    existing_ids = existing_ids or set()
    used_ids = used_ids or set()

    base_id = support_id_from_url(url, name)
    rarity_text = clean_text(rarity).lower()
    type_text = normalize_support_type(support_type)

    if rarity_text in ["sr", "r"] and not base_id.endswith("_" + rarity_text):
        base_id = base_id + "_" + rarity_text

    if type_text not in ["", "all", "speed"]:
        type_suffix = "_" + type_text

        if not base_id.endswith(type_suffix):
            base_id = base_id + type_suffix

    candidates = [base_id]

    number = get_gametora_number_from_url(url)

    if number:
        candidates.append(base_id + "_" + number)

    for candidate in candidates:
        if candidate not in existing_ids and candidate not in used_ids:
            used_ids.add(candidate)
            return candidate

    index = 2

    while True:
        candidate = base_id + "_" + str(index)

        if number:
            candidate = base_id + "_" + number + "_" + str(index)

        if candidate not in existing_ids and candidate not in used_ids:
            used_ids.add(candidate)
            return candidate

        index += 1


def get_gametora_number_from_url(url):
    match = re.search(r"/supports/(\d+)-", url)

    if match:
        return match.group(1)

    return ""


def unique_keep_order(items):
    seen = set()
    result = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def read_existing_keys(csv_path, key_fields):
    keys = set()

    if not csv_path.exists():
        return keys

    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            key = tuple(row.get(field, "").strip() for field in key_fields)
            keys.add(key)

    return keys


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            safe_row = {}

            for field in fieldnames:
                safe_row[field] = row.get(field, "")

            writer.writerow(safe_row)


def append_unique_csv(path, fieldnames, new_rows, key_fields):
    old_rows = []
    existing = set()

    if path.exists():
        with path.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            for row in reader:
                old_rows.append(row)
                key = tuple(row.get(field, "").strip() for field in key_fields)
                existing.add(key)

    added = 0

    for row in new_rows:
        key = tuple(row.get(field, "").strip() for field in key_fields)

        if key in existing:
            continue

        old_rows.append(row)
        existing.add(key)
        added += 1

    write_csv(path, fieldnames, old_rows)
    return added


# =========================
# PLAYWRIGHT HELPERS
# =========================


def get_visible_lines(page):
    text = page.evaluate("() => document.body.innerText")
    return split_lines(text)


def scroll_to_bottom(page, max_rounds=18):
    last_height = 0
    stable_count = 0

    for _ in range(max_rounds):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(550)
        current_height = page.evaluate("() => document.body.scrollHeight")

        if current_height == last_height:
            stable_count += 1
        else:
            stable_count = 0

        if stable_count >= 2:
            break

        last_height = current_height


def collect_filtered_links_by_scrolling(page, max_rounds=80):
    """
    Dùng cho manual-filter.

    Bạn lọc sẵn trên GameTora, rồi hàm này sẽ cuộn qua danh sách đã lọc
    và chỉ gom các card thật sự xuất hiện trên màn hình trong lúc cuộn.

    Khác với collect_support_links(..., viewport_only=True):
    - viewport_only=True chỉ lấy màn hình hiện tại nên dễ bị thiếu, ví dụ chỉ 22/48.
    - hàm này lấy lần lượt từng viewport khi cuộn xuống nên lấy đủ list đã lọc.

    Quan trọng: nó không lấy toàn bộ database bị ẩn bởi filter, vì mỗi vòng chỉ lấy
    những card đang visible trong viewport.
    """
    links = []
    seen = set()

    def add_current_viewport_links():
        current_links = collect_support_links(page, visible_only=True, viewport_only=True)
        added = 0

        for link in current_links:
            if link not in seen:
                seen.add(link)
                links.append(link)
                added += 1

        return added

    # QUAN TRỌNG:
    # Sau khi bạn lọc xong, có thể browser đang đứng ở giữa/cuối danh sách.
    # Nếu bắt đầu gom link ngay tại vị trí đó thì sẽ bị thiếu các card phía trên.
    # Vì vậy manual-filter phải kéo về đầu trang/list trước, rồi mới cuộn xuống gom toàn bộ card đã lọc.
    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(900)

    add_current_viewport_links()

    last_y = -1
    last_height = -1
    stable_rounds = 0

    for _ in range(max_rounds):
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(650)
        add_current_viewport_links()

        y = page.evaluate("() => Math.round(window.scrollY)")
        height = page.evaluate("() => Math.round(document.body.scrollHeight)")

        if y == last_y and height == last_height:
            stable_rounds += 1
        else:
            stable_rounds = 0

        # Nếu cuộn 3 lần mà không đi thêm được thì xem như đến cuối list.
        if stable_rounds >= 3:
            break

        last_y = y
        last_height = height

    return links


def try_click_show_upcoming(page):
    # GameTora có checkbox "Show upcoming supports".
    # Nếu cấu trúc web đổi thì đoạn này fail nhẹ, không làm chết crawler.
    candidates = [
        "label:has-text('Show upcoming supports')",
        "text=Show upcoming supports",
    ]

    for selector in candidates:
        try:
            locator = page.locator(selector).first

            if locator.count() > 0:
                locator.click(timeout=1200)
                page.wait_for_timeout(700)
                return True
        except Exception:
            pass

    return False


def collect_support_links(page, visible_only=True, viewport_only=False):
    """
    Lấy link support card từ trang list.

    visible_only=True:
        Chỉ lấy card đang hiện bằng CSS.

    viewport_only=True:
        Chỉ lấy card đang nằm trong màn hình hiện tại của browser.
        Cái này dùng cho manual-filter để tránh crawler lấy cả database JP/upcoming
        nằm ngoài vùng bạn đang nhìn thấy.
    """
    return page.evaluate(
        """
        ({ visibleOnly, viewportOnly }) => {
            const isVisible = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0
                    && r.height > 0
                    && style.visibility !== 'hidden'
                    && style.display !== 'none'
                    && style.opacity !== '0';
            };

            const getCardBox = (a) => {
                const candidates = [];

                // Ưu tiên vùng link/card gần nhất thay vì lấy body/div quá lớn.
                candidates.push(a);

                let current = a.parentElement;
                while (current && current !== document.body) {
                    const r = current.getBoundingClientRect();
                    const style = window.getComputedStyle(current);

                    if (
                        r.width > 40 && r.height > 40 &&
                        r.width < window.innerWidth * 0.95 &&
                        r.height < window.innerHeight * 0.95 &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        style.opacity !== '0'
                    ) {
                        candidates.push(current);
                    }

                    current = current.parentElement;
                }

                candidates.sort((x, y) => {
                    const rx = x.getBoundingClientRect();
                    const ry = y.getBoundingClientRect();
                    return (rx.width * rx.height) - (ry.width * ry.height);
                });

                for (const el of candidates) {
                    if (isVisible(el)) {
                        return el.getBoundingClientRect();
                    }
                }

                return a.getBoundingClientRect();
            };

            const isInViewport = (rect) => {
                // Chỉ cần card giao với màn hình hiện tại là tính.
                // Chừa 20px để không lấy card nằm sát mép bị che mất.
                return rect.bottom > 20
                    && rect.top < window.innerHeight - 20
                    && rect.right > 20
                    && rect.left < window.innerWidth - 20;
            };

            const anchors = Array.from(document.querySelectorAll('a[href*="/umamusume/supports/"]'));
            const result = [];
            const seen = new Set();

            for (const a of anchors) {
                const href = new URL(a.getAttribute('href'), location.origin).href;

                if (!new RegExp('/umamusume/supports/[0-9]+-').test(href)) {
                    continue;
                }

                if (seen.has(href)) {
                    continue;
                }

                if (visibleOnly) {
                    const card = a.closest('article, li, .card, [class*=card], div');
                    if (!isVisible(a) && !isVisible(card)) {
                        continue;
                    }
                }

                const rect = getCardBox(a);

                if (viewportOnly && !isInViewport(rect)) {
                    continue;
                }

                seen.add(href);
                result.push({
                    href,
                    top: rect.top + window.scrollY,
                    left: rect.left + window.scrollX,
                });
            }

            result.sort((a, b) => a.top - b.top || a.left - b.left);
            return result.map(item => item.href);
        }
        """,
        {
            "visibleOnly": visible_only,
            "viewportOnly": viewport_only,
        },
    )

def guess_support_type(page):
    return page.evaluate(
        """
        () => {
            const types = ['speed', 'stamina', 'power', 'guts', 'wit', 'intelligence', 'friend', 'group'];
            const normalizeType = (value) => {
                value = (value || '').toLowerCase();
                if (value.includes('intelligence')) return 'wit';
                for (const type of types) {
                    if (value.includes(type)) {
                        return type === 'intelligence' ? 'wit' : type;
                    }
                }
                return '';
            };
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const all = Array.from(document.querySelectorAll('body *')).filter(isVisible);
            const typeLabel = all.find(el => (el.innerText || '').trim().toLowerCase() === 'type');

            if (typeLabel) {
                const index = all.indexOf(typeLabel);
                const afterType = all.slice(index, index + 45);

                for (const el of afterType) {
                    const imgs = el.querySelectorAll ? Array.from(el.querySelectorAll('img')) : [];

                    for (const img of imgs) {
                        const text = [
                            img.alt,
                            img.title,
                            img.src,
                            img.getAttribute('aria-label'),
                            img.className,
                        ].join(' ');
                        const type = normalizeType(text);

                        if (type) {
                            return type;
                        }
                    }

                    const text = [
                        el.getAttribute('aria-label'),
                        el.className,
                        el.getAttribute('title'),
                    ].join(' ');
                    const type = normalizeType(text);

                    if (type) {
                        return type;
                    }
                }
            }

            const metaText = Array.from(document.querySelectorAll('meta'))
                .map(meta => meta.getAttribute('content') || '')
                .join(' ');
            let type = normalizeType(metaText);

            if (type) {
                return type;
            }

            const titleType = normalizeType(document.title || '');

            if (titleType) {
                return titleType;
            }

            const imgs = Array.from(document.images);

            for (const img of imgs) {
                const text = [img.alt, img.title, img.src, img.className].join(' ');
                type = normalizeType(text);

                if (type) {
                    return type;
                }
            }

            return '';
        }
        """
    )


def get_card_image_url(page):
    return page.evaluate(
        """
        () => {
            const imgs = Array.from(document.images);

            const supportImg = imgs.find(img => {
                const text = [img.alt, img.title, img.src].join(' ').toLowerCase();
                return text.includes('support card') && !text.includes('icon');
            });

            if (supportImg) {
                return supportImg.src;
            }

            const bigImgs = imgs
                .map(img => {
                    const r = img.getBoundingClientRect();
                    return {
                        src: img.src,
                        area: r.width * r.height,
                    };
                })
                .filter(item => item.area > 10000)
                .sort((a, b) => b.area - a.area);

            if (bigImgs.length > 0) {
                return bigImgs[0].src;
            }

            return '';
        }
        """
    )


def download_image(url, output_path):
    if not url or requests is None:
        return False

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return True
    except Exception:
        return False


# =========================
# TEXT PARSING
# =========================


def extract_h1_name_and_rarity(lines):
    name = ""
    rarity = ""

    for line in lines:
        match = re.match(r"^(.+?)\s*\((SSR|SR|R)\)\s+Support Card$", line, re.IGNORECASE)

        if match:
            name = clean_line(match.group(1))
            rarity = match.group(2).upper()
            return name, rarity

    for line in lines:
        if "Support Card" in line:
            rarity_match = re.search(r"\((SSR|SR|R)\)", line, re.IGNORECASE)
            rarity = rarity_match.group(1).upper() if rarity_match else ""
            name = re.sub(r"\s*\((SSR|SR|R)\).*", "", line, flags=re.IGNORECASE).strip()
            name = name.replace("Support Card", "").strip()
            return name, rarity

    return name, rarity


def extract_card_title(lines):
    for line in lines:
        if re.match(r"^\[.+\]$", line):
            return line

    return ""


def extract_release_date(lines):
    for index, line in enumerate(lines):
        if line.lower() == "release date":
            for next_line in lines[index + 1:index + 5]:
                match = re.search(r"\d{4}-\d{2}-\d{2}", next_line)

                if match:
                    return match.group(0)

    for line in lines:
        match = re.search(r"\d{4}-\d{2}-\d{2}", line)

        if match:
            return match.group(0)

    return ""


def match_effect_line(line):
    line = clean_line(line)

    for effect_name in SUPPORT_EFFECT_NAMES:
        pattern = r"^" + re.escape(effect_name) + r"\s*(.*)$"
        match = re.match(pattern, line, re.IGNORECASE)

        if match:
            value = clean_line(match.group(1))
            return effect_name, value

    return None, None


def extract_unique_effect(lines):
    try:
        start = lines.index("Unique Effect")
    except ValueError:
        return ""

    unique_lines = []

    for line in lines[start + 1:]:
        effect_name, _ = match_effect_line(line)

        if effect_name:
            break

        if line in ["Support hints", "Stat gain", "Skills from events", "Training Events"]:
            break

        # Bỏ các dòng UI của level control nếu dính vào.
        if re.match(r"^(Level \d+|\+\d+|-\d+|◇+)$", line):
            continue

        unique_lines.append(line)

    return "|".join(unique_lines)


def extract_effects_current_level(lines):
    effects = {}

    if "Unique Effect" in lines:
        start = lines.index("Unique Effect") + 1
    elif "Support effects" in lines:
        start = lines.index("Support effects") + 1
    else:
        start = 0

    stop_titles = [
        "Support hints",
        "Stat gain",
        "Skills from events",
        "Training Events",
        "Character Rate Up",
        "Support Rate Up",
        "Newest Scenario",
    ]

    for line in lines[start:]:
        if line in stop_titles:
            break

        effect_name, value = match_effect_line(line)

        if not effect_name:
            continue

        effects[effect_name] = normalize_effect_value(value)

    return effects


def get_current_support_level(lines):
    for line in lines:
        match = re.match(r"^Level\s+(\d+)$", line, re.IGNORECASE)

        if match:
            return int(match.group(1))

    return None


def get_current_support_level_from_page(page):
    """
    Đọc level đang HIỂN THỊ trên GameTora, ví dụ: Level 30, Level 35...
    Không dùng document.body.innerText trước, vì một số web có thể giữ text cũ/ẩn trong DOM.
    """
    try:
        level = page.evaluate(
            r"""
            () => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return r.width > 0
                        && r.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && style.opacity !== '0';
                };

                const items = Array.from(document.querySelectorAll('body *'))
                    .filter(isVisible)
                    .map(el => {
                        const text = (el.innerText || el.textContent || '').trim();
                        const match = text.match(/^Level\s+(\d+)$/i);

                        if (!match) return null;

                        const r = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);

                        return {
                            level: parseInt(match[1], 10),
                            top: r.top,
                            left: r.left,
                            area: r.width * r.height,
                            fontSize: parseFloat(style.fontSize || '0'),
                        };
                    })
                    .filter(Boolean)
                    .sort((a, b) => {
                        // Ưu tiên text Level nằm gần phía trên trang và có font lớn hơn.
                        if (Math.abs(a.top - b.top) > 5) return a.top - b.top;
                        return b.fontSize - a.fontSize || b.area - a.area;
                    });

                if (items.length > 0) {
                    return items[0].level;
                }

                return null;
            }
            """
        )

        if level is not None:
            return int(level)
    except Exception:
        pass

    return get_current_support_level(get_visible_lines(page))


def scroll_level_controls_into_view(page):
    """
    Đưa cụm Level 30/35/40... lên giữa màn hình trước khi bấm +5/-5.
    Lỗi bạn gặp là crawler tìm thấy nút +5 trong DOM nhưng nó đang nằm ngoài viewport,
    nên page.mouse.click(x, y) không bấm đúng nút.
    """
    try:
        return page.evaluate(
            r"""
            () => {
                const getText = (el) => (el.innerText || el.textContent || '').trim();
                const levelEl = Array.from(document.querySelectorAll('body *'))
                    .find(el => /^Level\s+\d+$/i.test(getText(el)));

                if (!levelEl) {
                    return false;
                }

                levelEl.scrollIntoView({ block: 'center', inline: 'center' });
                return true;
            }
            """
        )
    except Exception:
        return False


def click_button_by_exact_text(page, text, expected_current_level=None):
    """
    Click thật vào nút +5/+1/-5/-1 của cụm Level.

    Bản này làm 3 lớp để chắc ăn hơn:
    1) Đưa cụm Level vào giữa màn hình.
    2) Tìm nút có text đúng và nằm gần dòng Level nhất.
    3) Click bằng tọa độ chuột trước. Nếu level chưa đổi thì dùng DOM click làm fallback.
    """
    try:
        scroll_level_controls_into_view(page)
        page.wait_for_timeout(250)

        target = page.evaluate(
            r"""
            ({ text }) => {
                const viewportW = window.innerWidth || document.documentElement.clientWidth;
                const viewportH = window.innerHeight || document.documentElement.clientHeight;

                const isUsable = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return r.width > 0
                        && r.height > 0
                        && r.bottom > 0
                        && r.right > 0
                        && r.top < viewportH
                        && r.left < viewportW
                        && style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && style.opacity !== '0'
                        && style.pointerEvents !== 'none';
                };

                const getText = (el) => (el.innerText || el.textContent || '').trim();

                const levelCandidates = Array.from(document.querySelectorAll('body *'))
                    .filter(isUsable)
                    .filter(el => /^Level\s+\d+$/i.test(getText(el)))
                    .map(el => {
                        const r = el.getBoundingClientRect();
                        return {
                            x: r.left + r.width / 2,
                            y: r.top + r.height / 2,
                            top: r.top,
                            bottom: r.bottom,
                            area: r.width * r.height,
                        };
                    })
                    .sort((a, b) => a.area - b.area);

                const levelPoint = levelCandidates.length > 0 ? levelCandidates[0] : null;

                const candidates = Array.from(document.querySelectorAll('button, [role="button"], a, div, span'))
                    .filter(isUsable)
                    .filter(el => getText(el) === text)
                    .map((el, index) => {
                        const r = el.getBoundingClientRect();
                        const tag = (el.tagName || '').toLowerCase();
                        const role = (el.getAttribute('role') || '').toLowerCase();
                        const className = String(el.className || '').toLowerCase();
                        const area = r.width * r.height;

                        let score = 0;

                        // Nút level của GameTora thường nhỏ và nằm ngang hàng với text Level.
                        if (r.width > 160 || r.height > 90) score += 1000;
                        if (r.width < 15 || r.height < 15) score += 300;
                        score += area * 0.01;

                        if (tag === 'button') score -= 300;
                        if (role === 'button') score -= 220;
                        if (className.includes('button') || className.includes('btn')) score -= 120;

                        if (levelPoint) {
                            const cx = r.left + r.width / 2;
                            const cy = r.top + r.height / 2;
                            score += Math.abs(cy - levelPoint.y) * 8 + Math.abs(cx - levelPoint.x) * 0.35;

                            // Nếu không nằm gần hàng level thì phạt mạnh.
                            if (Math.abs(cy - levelPoint.y) > 90) score += 2000;
                        }

                        return {
                            index,
                            x: r.left + r.width / 2,
                            y: r.top + r.height / 2,
                            score,
                            width: r.width,
                            height: r.height,
                            tag,
                        };
                    })
                    .sort((a, b) => a.score - b.score);

                if (candidates.length === 0) {
                    return null;
                }

                return candidates[0];
            }
            """,
            {"text": text},
        )

        if not target:
            print(f"[LEVEL CLICK] Không tìm thấy nút {text}")
            return False

        before_level = get_current_support_level_from_page(page)

        print(
            f"[LEVEL CLICK] mouse bấm {text} tại x={target['x']:.0f}, y={target['y']:.0f} "
            f"| before=Lv.{before_level}"
        )
        page.mouse.click(target["x"], target["y"])
        page.wait_for_timeout(450)

        after_mouse_level = get_current_support_level_from_page(page)

        if before_level is None or after_mouse_level != before_level:
            return True

        # Fallback: nếu mouse click không làm level đổi, click trực tiếp vào element gần Level nhất bằng DOM.
        dom_clicked = page.evaluate(
            r"""
            ({ text }) => {
                const viewportW = window.innerWidth || document.documentElement.clientWidth;
                const viewportH = window.innerHeight || document.documentElement.clientHeight;

                const isUsable = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return r.width > 0
                        && r.height > 0
                        && r.bottom > 0
                        && r.right > 0
                        && r.top < viewportH
                        && r.left < viewportW
                        && style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && style.opacity !== '0'
                        && style.pointerEvents !== 'none';
                };

                const getText = (el) => (el.innerText || el.textContent || '').trim();

                const levelEl = Array.from(document.querySelectorAll('body *'))
                    .filter(isUsable)
                    .filter(el => /^Level\s+\d+$/i.test(getText(el)))
                    .map(el => {
                        const r = el.getBoundingClientRect();
                        return { el, x: r.left + r.width / 2, y: r.top + r.height / 2, area: r.width * r.height };
                    })
                    .sort((a, b) => a.area - b.area)[0];

                const candidates = Array.from(document.querySelectorAll('button, [role="button"], a, div, span'))
                    .filter(isUsable)
                    .filter(el => getText(el) === text)
                    .map(el => {
                        const r = el.getBoundingClientRect();
                        const tag = (el.tagName || '').toLowerCase();
                        const role = (el.getAttribute('role') || '').toLowerCase();
                        const className = String(el.className || '').toLowerCase();
                        const cx = r.left + r.width / 2;
                        const cy = r.top + r.height / 2;
                        let score = 0;

                        if (r.width > 160 || r.height > 90) score += 1000;
                        score += r.width * r.height * 0.01;
                        if (tag === 'button') score -= 300;
                        if (role === 'button') score -= 220;
                        if (className.includes('button') || className.includes('btn')) score -= 120;

                        if (levelEl) {
                            score += Math.abs(cy - levelEl.y) * 8 + Math.abs(cx - levelEl.x) * 0.35;
                            if (Math.abs(cy - levelEl.y) > 90) score += 2000;
                        }

                        return { el, score };
                    })
                    .sort((a, b) => a.score - b.score);

                if (candidates.length === 0) return false;

                const el = candidates[0].el;
                el.scrollIntoView({ block: 'center', inline: 'center' });
                el.click();
                return true;
            }
            """,
            {"text": text},
        )

        if dom_clicked:
            page.wait_for_timeout(500)
            after_dom_level = get_current_support_level_from_page(page)
            print(f"[LEVEL CLICK] DOM fallback {text} | after=Lv.{after_dom_level}")
            return before_level is None or after_dom_level != before_level

        return False
    except Exception as error:
        print(f"[LEVEL CLICK ERROR] {text}: {error}")
        return False


def set_support_level(page, target_level):
    """
    Chuyển level bằng các nút +5/+1/-5/-1 rồi đợi text Level đổi thật.
    """
    for _ in range(40):
        current = get_current_support_level_from_page(page)

        if current is None:
            return None

        if current == target_level:
            return current

        if current < target_level:
            button = "+5" if target_level - current >= 5 else "+1"
        else:
            button = "-5" if current - target_level >= 5 else "-1"

        clicked = click_button_by_exact_text(page, button, expected_current_level=current)

        if not clicked:
            print(f"[LEVEL WARN] Bấm {button} không đổi level. current=Lv.{current}, target=Lv.{target_level}")
            return current

        # Đợi UI cập nhật sau khi bấm nút cộng/trừ.
        for _ in range(25):
            page.wait_for_timeout(120)
            new_level = get_current_support_level_from_page(page)

            if new_level == target_level:
                return new_level

            if new_level is not None and new_level != current:
                break

    return get_current_support_level_from_page(page)


def reset_support_level_to_lowest(page):
    """
    Trước khi đọc bảng, kéo level về thấp nhất của card hiện tại.
    SSR thường thấp nhất 30, SR là 25, R là 20.
    Không cần biết trước rarity; cứ bấm -5 đến khi không xuống được nữa.
    """
    last_level = None

    for _ in range(12):
        current = get_current_support_level_from_page(page)

        if current is None:
            return None

        if current == last_level:
            return current

        clicked = click_button_by_exact_text(page, "-5", expected_current_level=current)

        if not clicked:
            return get_current_support_level_from_page(page)

        page.wait_for_timeout(350)
        new_level = get_current_support_level_from_page(page)

        if new_level is None or new_level == current:
            return current

        last_level = current

    return get_current_support_level_from_page(page)


def extract_effect_rows(page, rarity):
    all_effects = {}
    target_levels = get_effect_level_targets_by_rarity(rarity)

    lowest_level = reset_support_level_to_lowest(page)
    print(f"[LEVEL START] rarity={rarity or '?'} lowest=Lv.{lowest_level} targets={target_levels}")

    for target_level, column in zip(target_levels, EFFECT_COLUMNS):
        actual_level = set_support_level(page, target_level)
        page.wait_for_timeout(700)

        lines = get_visible_lines(page)
        effects = extract_effects_current_level(lines)

        print(f"[LEVEL] target=Lv.{target_level} actual=Lv.{actual_level} column={column} effects={len(effects)}")

        for effect_name, value in effects.items():
            if effect_name not in all_effects:
                all_effects[effect_name] = {
                    "effect_name": effect_name,
                    "lb0": "",
                    "lb1": "",
                    "lb2": "",
                    "lb3": "",
                    "lb4": "",
                }

            all_effects[effect_name][column] = value

    return list(all_effects.values())


# =========================
# SECTION / SKILL PARSING
# =========================



def extract_skill_section_snapshot(page, section_title, stop_titles):
    """
    Lấy href skill + text skill nằm giữa section_title và stop_titles.
    Không lấy toàn database, chỉ đọc section trên trang detail của card đang mở.
    """
    return page.evaluate(
        r"""
        ({ sectionTitle, stopTitles }) => {
            const normalize = (text) => (text || '')
                .replace(/\u00a0/g, ' ')
                .replace(/\s+/g, ' ')
                .trim()
                .toLowerCase();

            const isVisible = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0
                    && r.height > 0
                    && style.visibility !== 'hidden'
                    && style.display !== 'none'
                    && style.opacity !== '0';
            };

            const exactText = (el) => (el.innerText || el.textContent || '').trim();
            const all = Array.from(document.querySelectorAll('body *')).filter(isVisible);
            const wantedSection = normalize(sectionTitle);

            const sectionCandidates = all
                .filter(el => normalize(exactText(el)) === wantedSection)
                .map(el => {
                    const r = el.getBoundingClientRect();
                    return {
                        top: r.top + window.scrollY,
                        area: r.width * r.height,
                        textLength: exactText(el).length,
                    };
                })
                .sort((a, b) => a.textLength - b.textLength || a.area - b.area || a.top - b.top);

            if (sectionCandidates.length === 0) {
                return { ok: false, sectionTop: 0, stopTop: 0, hrefs: [], texts: [] };
            }

            const sectionTop = sectionCandidates[0].top;
            let stopTop = Number.POSITIVE_INFINITY;

            for (const stopTitle of stopTitles) {
                const wantedStop = normalize(stopTitle);
                const stopCandidates = all
                    .filter(el => normalize(exactText(el)) === wantedStop)
                    .map(el => {
                        const r = el.getBoundingClientRect();
                        return {
                            top: r.top + window.scrollY,
                            area: r.width * r.height,
                            textLength: exactText(el).length,
                        };
                    })
                    .filter(item => item.top > sectionTop + 5)
                    .sort((a, b) => a.top - b.top || a.textLength - b.textLength || a.area - b.area);

                if (stopCandidates.length > 0) {
                    stopTop = Math.min(stopTop, stopCandidates[0].top);
                }
            }

            if (!Number.isFinite(stopTop)) {
                stopTop = document.body.scrollHeight;
            }

            const isInsideSection = (el) => {
                if (!isVisible(el)) return false;
                const r = el.getBoundingClientRect();
                const top = r.top + window.scrollY;
                return top > sectionTop + 2 && top < stopTop - 2;
            };

            const hrefs = Array.from(document.querySelectorAll('a[href*="/umamusume/skills/"]'))
                .filter(isInsideSection)
                .map(a => new URL(a.getAttribute('href'), location.origin).href);

            const texts = [];
            const seenText = new Set();

            for (const el of all) {
                if (!isInsideSection(el)) continue;

                const rawText = exactText(el);
                if (!rawText || rawText.length > 500) continue;

                const lines = rawText
                    .split(String.fromCharCode(10))
                    .map(line => line.replace(/\s+/g, ' ').trim())
                    .filter(Boolean);

                for (const line of lines) {
                    if (line.length > 90) continue;
                    if (line === 'Details' || line === 'More') continue;

                    const key = line.toLowerCase();
                    if (!seenText.has(key)) {
                        seenText.add(key);
                        texts.push(line);
                    }
                }
            }

            return {
                ok: true,
                sectionTop,
                stopTop,
                hrefs: Array.from(new Set(hrefs)),
                texts,
            };
        }
        """,
        {"sectionTitle": section_title, "stopTitles": stop_titles},
    )


def extract_skill_ids_from_section(page, section_title, stop_titles):
    """
    Đọc toàn bộ skill trong section Support hints / Skills from events của card đang mở.

    Cách đọc:
    - Ưu tiên lấy link /umamusume/skills/... nếu GameTora có gắn link.
    - Nếu thiếu link thì lấy text tên skill và map qua skills.csv.
    - Chỉ đọc trong vùng giữa section_title và stop_titles, không đụng tới list card JP/global ở trang ngoài.
    """
    skill_ids = []
    seen = set()

    snapshot = extract_skill_section_snapshot(page, section_title, stop_titles)

    if not snapshot.get("ok"):
        print(f"[SKILL WARN] Không tìm thấy section: {section_title}")
        return []

    section_top = int(snapshot.get("sectionTop", 0))
    stop_top = int(snapshot.get("stopTop", 0))

    # Kéo tới đầu section để các skill item/link được render đầy đủ.
    page.evaluate("(y) => window.scrollTo(0, Math.max(0, y - 120))", section_top)
    page.wait_for_timeout(650)

    for _ in range(16):
        snapshot = extract_skill_section_snapshot(page, section_title, stop_titles)

        for href in snapshot.get("hrefs", []):
            skill_id = skill_id_from_skill_url(href)

            if skill_id and skill_id not in seen:
                seen.add(skill_id)
                skill_ids.append(skill_id)

        for line in snapshot.get("texts", []):
            skill_id = skill_id_from_visible_text(line)

            if skill_id and skill_id not in seen:
                seen.add(skill_id)
                skill_ids.append(skill_id)

        current_y = page.evaluate("() => window.scrollY")
        viewport_h = page.evaluate("() => window.innerHeight")

        if current_y + viewport_h >= stop_top - 80:
            break

        page.mouse.wheel(0, 600)
        page.wait_for_timeout(350)

    print(f"[SKILLS] {section_title}: {len(skill_ids)} -> {'|'.join(skill_ids)}")
    return skill_ids


def extract_text_between_titles(lines, start_title, stop_titles):
    if start_title not in lines:
        return []

    start = lines.index(start_title) + 1
    result = []

    for line in lines[start:]:
        if line in stop_titles:
            break

        # bỏ vài dòng note/link không cần lưu trong CSV.
        if line in ["Details", "More"]:
            continue

        result.append(line)

    return result


def extract_stat_gain(lines):
    stat_lines = extract_text_between_titles(
        lines,
        "Stat gain",
        SECTION_STOP_TITLES["stat_gain"],
    )

    filtered = []

    for line in stat_lines:
        if re.search(r"^(Speed|Stamina|Power|Guts|Wit|Skill Pt|Skill Points?)\b", line, re.IGNORECASE):
            filtered.append(line)

    return "|".join(filtered)


# =========================
# TRAINING EVENT PARSING
# =========================


def get_training_event_button_titles(page, group_title):
    return page.evaluate(
        """
        ({ groupTitle }) => {
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const all = Array.from(document.querySelectorAll('body *')).filter(isVisible);
            const exact = (el) => (el.innerText || '').trim();
            const group = all.find(el => exact(el) === groupTitle);

            if (!group) {
                return [];
            }

            const groupTop = group.getBoundingClientRect().top + window.scrollY;
            const possibleStops = ['Chain Events', 'Random Events', 'Character Rate Up', 'Support Rate Up', 'Newest Scenario'];
            let stopTop = Number.POSITIVE_INFINITY;

            for (const title of possibleStops) {
                if (title === groupTitle) {
                    continue;
                }

                const stop = all.find(el => {
                    const top = el.getBoundingClientRect().top + window.scrollY;
                    return top > groupTop && exact(el) === title;
                });

                if (stop) {
                    stopTop = Math.min(stopTop, stop.getBoundingClientRect().top + window.scrollY);
                }
            }

            const buttons = Array.from(document.querySelectorAll('button, [role="button"]'))
                .filter(isVisible)
                .filter(btn => {
                    const top = btn.getBoundingClientRect().top + window.scrollY;
                    return top > groupTop && top < stopTop;
                })
                .map(btn => exact(btn))
                .filter(text => text.length > 0);

            return Array.from(new Set(buttons));
        }
        """,
        {"groupTitle": group_title},
    )


def click_event_button(page, title):
    return page.evaluate(
        """
        (title) => {
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const buttons = Array.from(document.querySelectorAll('button, [role="button"]'))
                .filter(isVisible)
                .filter(btn => (btn.innerText || '').trim() === title);

            if (buttons.length > 0) {
                buttons[0].click();
                return true;
            }

            return false;
        }
        """,
        title,
    )


def extract_active_event_text(page, title):
    return page.evaluate(
        """
        ({ title }) => {
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const candidates = Array.from(document.querySelectorAll('body *'))
                .filter(isVisible)
                .map(el => {
                    const r = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    return {
                        text,
                        area: r.width * r.height,
                        top: r.top + window.scrollY,
                    };
                })
                .filter(item => {
                    if (!item.text.includes(title)) return false;
                    if (item.text === title) return false;
                    if (item.text.length > 1800) return false;
                    if (item.text.split(String.fromCharCode(10)).length < 2) return false;
                    return true;
                })
                .sort((a, b) => a.area - b.area || a.text.length - b.text.length);

            if (candidates.length > 0) {
                return candidates[0].text;
            }

            return '';
        }
        """,
        {"title": title},
    )


def mark_event_note_lines(line):
    lower = line.lower().strip()

    orange_lines = {
        "randomly either",
        "or",
        "event chain ended",
    }

    if lower in orange_lines:
        return "!" + line

    return line


def normalize_choice_label(line):
    lower = line.lower().strip()

    if lower in ["top", "upper"]:
        return "Top"

    if lower in ["bottom", "bot", "lower"]:
        return "Bot"

    if lower in ["middle", "mid"]:
        return "Mid"

    return ""


def event_text_to_detail(raw_text, title):
    lines = split_lines(raw_text)

    cleaned = []
    clean_title = re.sub(r"^\([^)]*\)\s*", "", title).strip()

    for line in lines:
        line = clean_line(line)

        # Bỏ title bị lặp trong card event.
        if line == title or line == clean_title:
            continue

        # Bỏ các dòng UI không cần.
        if line in ["Details", "More"]:
            continue

        if line.startswith("Training Events"):
            continue

        # Bỏ dòng bị dính nguyên danh sách chain event:
        # Ví dụ: (›) Event 1(››) Event 2(›››) Event 3
        arrow_count = line.count("(›") + line.count("(❯")

        if arrow_count >= 2:
            continue

        # Bỏ dòng chỉ là ký hiệu event, ví dụ: (›), (››), (›››)
        if re.match(r"^\((›|❯)+\)$", line):
            continue

        cleaned.append(mark_event_note_lines(line))

    # Nếu có Top/Bot thì dùng format mới: Top::...||Bot::...
    blocks = []
    index = 0

    while index < len(cleaned):
        label = normalize_choice_label(cleaned[index].lstrip("!"))

        if not label:
            index += 1
            continue

        index += 1
        block_lines = []

        while index < len(cleaned) and not normalize_choice_label(cleaned[index].lstrip("!")):
            block_lines.append(cleaned[index])
            index += 1

        if block_lines:
            blocks.append(label + "::" + "|".join(block_lines))

    if blocks:
        return "||".join(blocks)

    return "|".join(cleaned)


def make_event_id(title):
    title = clean_line(title)
    title_no_prefix = re.sub(r"^\([^)]*\)\s*", "", title).strip()
    title_no_star = title_no_prefix.replace("☆", "").replace("★", "").strip()

    lesson_match = re.match(r"^(Lesson\s+\w+)", title_no_star, re.IGNORECASE)

    if lesson_match:
        return text_to_id(lesson_match.group(1))

    return text_to_id(title_no_star)


def extract_training_events(page, card_id):
    event_rows = []

    for section, group_title in [("chain", "Chain Events"), ("random", "Random Events")]:
        titles = get_training_event_button_titles(page, group_title)

        for sort_index, title in enumerate(titles, start=1):
            clicked = click_event_button(page, title)

            if not clicked:
                continue

            page.wait_for_timeout(500)
            raw_event_text = extract_active_event_text(page, title)
            detail = event_text_to_detail(raw_event_text, title)

            # Nếu GameTora đổi DOM làm crawler chưa lấy được body event,
            # vẫn giữ title để bạn biết event nào bị thiếu và sửa tay sau.
            event_rows.append(
                {
                    "card_id": card_id,
                    "section": section,
                    "event_id": make_event_id(title),
                    "title": title,
                    "detail": detail,
                    "sort_order": sort_index,
                }
            )

    return event_rows


# =========================
# CLICK CARD FROM LIST PAGE
# =========================


def click_support_card_from_list(page, target_url):
    """
    Click thật vào thẻ support card trên trang list.

    Không dùng page.goto() ở bước mở card.
    Không dùng anchor.click() JS nữa, vì nhìn trên browser giống như không bấm.
    Hàm này lấy tọa độ ảnh/card rồi dùng page.mouse.click(x, y).
    """
    target_path = urlparse(target_url).path.rstrip("/")

    # Đi từ đầu trang/list để không bị kẹt ở giữa/cuối trang sau khi đọc card trước đó.
    try:
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
    except Exception:
        pass

    for _ in range(70):
        click_point = page.evaluate(
            """
            ({ targetPath }) => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return r.width > 0
                        && r.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && style.opacity !== '0';
                };

                const boxOf = (el) => {
                    const r = el.getBoundingClientRect();
                    return {
                        x: r.left + r.width / 2,
                        y: r.top + r.height / 2,
                        width: r.width,
                        height: r.height,
                        area: r.width * r.height,
                    };
                };

                const anchors = Array.from(document.querySelectorAll('a[href*="/umamusume/supports/"]'));

                const anchor = anchors.find(a => {
                    const url = new URL(a.getAttribute('href'), location.origin);
                    const path = url.pathname.replace(/[/]$/, '');

                    if (path !== targetPath) return false;

                    if (isVisible(a)) return true;

                    const card = a.closest('article, li, .card, [class*=card], div');
                    return isVisible(card);
                });

                if (!anchor) {
                    return null;
                }

                anchor.scrollIntoView({ block: 'center', inline: 'center' });

                const imageCandidates = Array.from(anchor.querySelectorAll('img'))
                    .filter(isVisible)
                    .map(img => ({ el: img, box: boxOf(img) }))
                    .filter(item => item.box.area > 400)
                    .sort((a, b) => b.box.area - a.box.area);

                if (imageCandidates.length > 0) {
                    return imageCandidates[0].box;
                }

                if (isVisible(anchor)) {
                    return boxOf(anchor);
                }

                const parents = [];
                let current = anchor.parentElement;

                while (current && current !== document.body) {
                    if (isVisible(current)) {
                        parents.push({ el: current, box: boxOf(current) });
                    }
                    current = current.parentElement;
                }

                parents.sort((a, b) => a.box.area - b.box.area);

                if (parents.length > 0) {
                    return parents[0].box;
                }

                return null;
            }
            """,
            {"targetPath": target_path},
        )

        if click_point:
            x = float(click_point["x"])
            y = float(click_point["y"])

            if 0 <= x <= 1440 and 0 <= y <= 1200:
                page.mouse.click(x, y)
            else:
                page.mouse.click(max(10, min(x, 1430)), max(10, min(y, 1190)))

            try:
                page.wait_for_url(re.compile(r".*/umamusume/supports/\d+-.*"), timeout=15000)
            except Exception:
                pass

            try:
                page.wait_for_load_state("domcontentloaded", timeout=60000)
            except Exception:
                pass

            page.wait_for_timeout(1500)
            return True

        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(350)

    return False

def go_back_to_support_list(page, start_url):
    try:
        page.go_back(wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(800)

        if "/umamusume/supports" in page.url and not re.search(r"/umamusume/supports/\d+-", page.url):
            return True
    except Exception:
        pass

    # Fallback cuối cùng. Manual filter có thể mất nếu GameTora không lưu filter,
    # nhưng vẫn tốt hơn là script chết giữa chừng.
    try:
        page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)
        return True
    except Exception:
        return False


# =========================
# CARD CRAWLING
# =========================


def crawl_one_card(page, url, args, already_open=False):
    if already_open:
        print(f"\n[READ AFTER CLICK] {url}")
        page.wait_for_load_state("domcontentloaded", timeout=60000)
        page.wait_for_timeout(500)
    else:
        print(f"\n[OPEN] {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(800)

    lines = get_visible_lines(page)
    name, rarity = extract_h1_name_and_rarity(lines)
    raw_card_id = support_id_from_url(url, name)
    support_type = guess_support_type(page)

    wanted_type = normalize_support_type(args.support_type)
    actual_type = normalize_support_type(support_type)

    # Chỉ skip Taiki khi bạn đang crawl Speed, vì Taiki Speed đã nhập tay.
    # Sang Stamina/Power/Guts/Wit thì KHÔNG skip theo tên cũ của Speed nữa.
    if (
        wanted_type == "speed"
        and not args.include_taiki
        and (raw_card_id in SKIP_CARD_IDS or name.lower().strip() in SKIP_CARD_NAMES)
    ):
        print(f"[SKIP] Đã có sẵn Taiki Speed: {name} ({raw_card_id})")
        return None

    if wanted_type != "all" and actual_type != wanted_type:
        print(f"[SKIP] Không phải {display_support_type(wanted_type)}: {name} | type={support_type}")
        return None

    card_id = make_unique_card_id(
        url=url,
        name=name,
        rarity=rarity,
        support_type=support_type or args.support_type,
        existing_ids=args.existing_card_ids,
        used_ids=args.used_card_ids,
    )

    if card_id != raw_card_id:
        print(f"[ID] raw={raw_card_id} -> csv_id={card_id}")

    card_title = extract_card_title(lines)
    release_date = extract_release_date(lines)
    unique_effect = extract_unique_effect(lines)
    image_url = get_card_image_url(page)
    image_filename = card_id + ".png"

    if args.download_images and image_url:
        ok = download_image(image_url, IMAGE_DIR / image_filename)
        print(f"[IMAGE] {image_filename}: {'OK' if ok else 'FAIL'}")

    hint_skill_ids = extract_skill_ids_from_section(
        page,
        "Support hints",
        SECTION_STOP_TITLES["support_hints"],
    )

    event_skill_ids = extract_skill_ids_from_section(
        page,
        "Skills from events",
        SECTION_STOP_TITLES["event_skills"],
    )

    lines = get_visible_lines(page)
    stat_gain = extract_stat_gain(lines)
    effect_rows = extract_effect_rows(page, rarity)
    event_rows = extract_training_events(page, card_id)

    for row in effect_rows:
        row["card_id"] = card_id

    card_row = {
        "id": card_id,
        "name": name,
        "title": card_title,
        "image": image_filename,
        "thumb_image": image_filename,
        "rarity": rarity,
        "type": display_support_type(support_type or args.support_type),
        "release_date": release_date,
        "unique_effect": unique_effect,
        "hint_skill_ids": "|".join(hint_skill_ids),
        "event_skill_ids": "|".join(event_skill_ids),
        # Tạm highlight skill event, bạn có thể sửa tay nếu muốn highlight ít hơn.
        "highlight_skill_ids": "|".join(event_skill_ids),
        "stat_gain": stat_gain,
        "stat_icon": "",
    }

    print(
        f"[OK] {name} | id={card_id} | effects={len(effect_rows)} | "
        f"hint_skills={len(hint_skill_ids)} | event_skills={len(event_skill_ids)} | events={len(event_rows)}"
    )

    return card_row, effect_rows, event_rows


# =========================
# MAIN
# =========================


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-url", default=DEFAULT_START_URL)
    parser.add_argument("--support-type", default="speed", choices=["speed", "stamina", "power", "guts", "wit", "friend", "group", "all"], help="Loại support muốn crawl")
    parser.add_argument("--manual-filter", action="store_true", help="Mở browser để bạn tự lọc trên GameTora, rồi bấm Enter mới crawl")
    parser.add_argument("--scan-filtered-list", action="store_true", help="Dùng chung với --manual-filter: tự cuộn hết list đã lọc để gom toàn bộ card. Mặc định KHÔNG bật, chỉ đọc card đang nằm trên màn hình hiện tại.")
    parser.add_argument("--append", action="store_true", help="Gộp trực tiếp vào 3 file CSV gốc")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn browser. Không dùng chung với --manual-filter")
    parser.add_argument("--download-images", action="store_true", help="Tải ảnh card vào static/images/support_cards")
    parser.add_argument("--skip-existing", action="store_true", help="Nếu bật thì skip card có raw id đã tồn tại. Mặc định KHÔNG skip để crawl Stamina/Power không bị thiếu do trùng tên với Speed.")
    parser.add_argument("--no-skip-existing", action="store_true", help="Giữ lại cho tương thích với lệnh cũ; bản này mặc định đã không skip existing.")
    parser.add_argument("--include-taiki", action="store_true", help="Không skip Taiki Shuttle Speed")
    parser.add_argument("--limit", type=int, default=0, help="Test nhanh vài card đầu tiên")
    args = parser.parse_args()

    existing_card_ids = set()

    if CARD_CSV.exists():
        existing_card_ids = {key[0] for key in read_existing_keys(CARD_CSV, ["id"])}

    args.existing_card_ids = existing_card_ids
    args.used_card_ids = set()

    card_rows = []
    effect_rows = []
    event_rows = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False if args.manual_filter else args.headless)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})

        print(f"[START] {args.start_url}")
        page.goto(args.start_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)

        if args.manual_filter:
            print("\n[MANUAL FILTER]")
            print("1) Ở browser Playwright vừa mở, bạn tự lọc support card trên GameTora.")
            print("2) Lọc Global + Type = Speed/Stamina/Power/Guts/Wit theo ý bạn.")
            print("3) MẶC ĐỊNH bản này chỉ gom các card đang nằm trên màn hình hiện tại, để tránh lôi card JP/upcoming bị ẩn.")
            print("4) Nếu muốn tự cuộn hết list đã lọc thì chạy thêm --scan-filtered-list.")
            input("5) Quay lại terminal này rồi bấm Enter để gom link và click từng card...")

            if args.scan_filtered_list:
                links = unique_keep_order(collect_filtered_links_by_scrolling(page))
                print(f"[FOUND] {len(links)} support card links trong TOÀN BỘ list đã lọc")
            else:
                links = unique_keep_order(collect_support_links(page, visible_only=True, viewport_only=True))
                print(f"[FOUND] {len(links)} support card links đang nằm trên màn hình hiện tại")
        else:
            try_click_show_upcoming(page)
            scroll_to_bottom(page)
            links = unique_keep_order(collect_support_links(page, visible_only=True, viewport_only=False))
            print(f"[FOUND] {len(links)} visible support card links trên toàn trang")

        filtered_links = []
        wanted_type_for_preskip = normalize_support_type(args.support_type)

        for url in links:
            raw_id = support_id_from_url(url)

            # Chỉ skip Taiki khi crawl Speed. Sang Stamina thì không được skip theo dữ liệu Speed cũ.
            if wanted_type_for_preskip == "speed" and not args.include_taiki and raw_id in SKIP_CARD_IDS:
                print(f"[PRE-SKIP] Taiki Speed: {raw_id}")
                continue

            # Mặc định KHÔNG skip existing, vì Stamina/Power/Guts có thể trùng tên với Speed.
            # Nếu thật sự muốn skip thì chạy thêm --skip-existing.
            if args.skip_existing and raw_id in existing_card_ids:
                print(f"[PRE-SKIP] Existing raw id: {raw_id}")
                continue

            filtered_links.append(url)

        links = filtered_links

        if args.limit > 0:
            links = links[:args.limit]
            print(f"[LIMIT] Chỉ crawl {args.limit} card sau khi lọc link")

        # KHÔNG mở detail_page riêng nữa.
        # Bản này dùng chính page list: click card -> đọc detail -> Back về list -> click card tiếp theo.
        for index, url in enumerate(links, start=1):
            raw_id = support_id_from_url(url)

            if wanted_type_for_preskip == "speed" and not args.include_taiki and raw_id in SKIP_CARD_IDS:
                print(f"[{index}/{len(links)}] Skip Taiki Speed: {raw_id}")
                continue

            if args.skip_existing and raw_id in existing_card_ids:
                print(f"[{index}/{len(links)}] Skip existing raw id: {raw_id}")
                continue

            try:
                print(f"\n[{index}/{len(links)}] CLICK card trên list: {url}")
                clicked = click_support_card_from_list(page, url)

                if not clicked:
                    print(f"[WARN] Không click được link đang visible, fallback bằng goto: {url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(800)

                result = crawl_one_card(page, url, args, already_open=True)

                if result is not None:
                    card_row, card_effect_rows, card_event_rows = result
                    card_rows.append(card_row)
                    effect_rows.extend(card_effect_rows)
                    event_rows.extend(card_event_rows)

            except PlaywrightTimeoutError:
                print(f"[ERROR] Timeout: {url}")
            except Exception as error:
                print(f"[ERROR] {url}")
                print(error)

            if index < len(links):
                back_ok = go_back_to_support_list(page, args.start_url)

                if not back_ok:
                    print("[ERROR] Không quay lại được support list, dừng crawler để tránh crawl sai filter.")
                    break

            time.sleep(0.5)

        browser.close()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_card_path = OUTPUT_DIR / CARD_CSV.name
    output_effect_path = OUTPUT_DIR / EFFECT_CSV.name
    output_event_path = OUTPUT_DIR / EVENT_CSV.name

    write_csv(output_card_path, CARD_HEADERS, card_rows)
    write_csv(output_effect_path, EFFECT_HEADERS, effect_rows)
    write_csv(output_event_path, EVENT_HEADERS, event_rows)

    print("\n[DONE] Đã xuất file kiểm tra:")
    print(f"- {output_card_path}")
    print(f"- {output_effect_path}")
    print(f"- {output_event_path}")
    print(f"\n[COUNT] cards={len(card_rows)}, effects={len(effect_rows)}, events={len(event_rows)}")

    if args.append:
        added_cards = append_unique_csv(CARD_CSV, CARD_HEADERS, card_rows, ["id"])
        added_effects = append_unique_csv(EFFECT_CSV, EFFECT_HEADERS, effect_rows, ["card_id", "effect_name"])
        added_events = append_unique_csv(EVENT_CSV, EVENT_HEADERS, event_rows, ["card_id", "section", "event_id"])

        print("\n[APPEND] Đã gộp vào 3 file CSV gốc:")
        print(f"- {CARD_CSV}: +{added_cards} rows")
        print(f"- {EFFECT_CSV}: +{added_effects} rows")
        print(f"- {EVENT_CSV}: +{added_events} rows")
    else:
        print("\n[NOTE] Script chưa đụng vào file CSV gốc.")
        print("Sau khi mở crawl_output kiểm tra thấy ổn, chạy:")
        print("python crawl_gametora_support_cards_visible_only_fixed_v10.py --manual-filter --support-type speed --append")


if __name__ == "__main__":
    main()
