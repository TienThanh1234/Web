import csv
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


URL = "https://gametora.com/umamusume/skills"
OUTPUT = "gametora_skills.csv"

COLUMNS = [
    "id",
    "name",
    "icon",
    "rarity",
    "description",
    "effect",
    "skill_points",
    "type",
    "parent_id",
    "required_sp",
    "category",
    "base_duration",
]


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def get_lines(text):
    if not text:
        return []

    lines = re.split(r"[\r\n]+", text)
    return [clean_text(line) for line in lines if clean_text(line)]


def slugify(text):
    text = text.replace("◎", "")
    text = text.replace("○", "")
    text = text.replace("◯", "")
    text = text.replace("〇", "")

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()

    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)

    return text.strip("_")


def remove_symbol(name):
    return clean_text(
        name.replace("◎", "")
            .replace("○", "")
            .replace("◯", "")
            .replace("〇", "")
    )


def is_probably_description(line):
    low = line.lower()

    keywords = [
        "increase",
        "decrease",
        "recover",
        "velocity",
        "acceleration",
        "endurance",
        "stamina",
        "straight",
        "corner",
        "race",
        "position",
        "performance",
        "slightly",
        "moderately",
        "greatly",
        "activate",
    ]

    return any(keyword in low for keyword in keywords)


def parse_card_text(card_text):
    lines = get_lines(card_text)

    skip = {
        "Image",
        "More",
        "Details",
        "Detailed view",
        "Compact view",
        "Normal",
        "Rare",
        "Unique",
    }

    lines = [line for line in lines if line not in skip]

    name = ""
    description = ""

    for i in range(len(lines) - 1):
        current_line = lines[i]
        next_line = lines[i + 1]

        if is_probably_description(next_line):
            name = current_line
            description = next_line
            break

    if not name or not description:
        return "", ""

    if len(name) > 100:
        return "", ""

    if "Found" in name and "results" in name:
        return "", ""

    return name, description


def get_card_data_from_more(more_locator):
    return more_locator.evaluate(
        """
        (el) => {
            let cur = el;

            for (let i = 0; i < 12 && cur; i++) {
                const text = (cur.innerText || "").trim();

                if (
                    text.includes("More") &&
                    text.length > 20 &&
                    text.length < 1200
                ) {
                    const img = cur.querySelector("img");

                    return {
                        text: text,
                        icon: img ? (img.getAttribute("src") || img.src || "") : ""
                    };
                }

                cur = cur.parentElement;
            }

            return {
                text: (el.innerText || "").trim(),
                icon: ""
            };
        }
        """
    )


def read_detail_text(page, skill_name):
    page.wait_for_timeout(700)

    return page.evaluate(
        """
        (skillName) => {
            const labels = [
                "effect",
                "effects",
                "base duration",
                "duration",
                "skill cost",
                "required sp",
                "skill points",
                "conditions",
                "condition",
                "show conditions"
            ];

            const elements = Array.from(document.querySelectorAll("body *"));
            const candidates = [];

            for (const el of elements) {
                const text = (el.innerText || "").trim();

                if (!text) continue;
                if (!text.includes(skillName)) continue;
                if (text.length < 40) continue;
                if (text.length > 5000) continue;

                const lower = text.toLowerCase();

                let score = 0;

                for (const label of labels) {
                    if (lower.includes(label)) {
                        score += 1;
                    }
                }

                candidates.push({
                    text: text,
                    score: score,
                    length: text.length
                });
            }

            candidates.sort((a, b) => {
                if (b.score !== a.score) return b.score - a.score;
                return a.length - b.length;
            });

            if (candidates.length > 0) {
                return candidates[0].text;
            }

            return document.body.innerText || "";
        }
        """,
        skill_name,
    )


def close_popup(page):
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
    except Exception:
        pass

    close_selectors = [
        "button:has-text('Close')",
        "button:has-text('×')",
        "button:has-text('✕')",
        "[aria-label='Close']",
    ]

    for selector in close_selectors:
        try:
            locator = page.locator(selector)

            if locator.count() > 0:
                locator.nth(locator.count() - 1).click(timeout=500)
                page.wait_for_timeout(250)
                return
        except Exception:
            pass


def value_after_label(text, labels):
    lines = get_lines(text)
    labels = [label.lower() for label in labels]

    for i, line in enumerate(lines):
        low = line.lower().strip(":")

        for label in labels:
            if low == label:
                if i + 1 < len(lines):
                    return lines[i + 1]

            if low.startswith(label + ":"):
                return clean_text(line.split(":", 1)[1])

    return ""


def parse_cost(detail_text):
    value = value_after_label(
        detail_text,
        [
            "skill cost",
            "cost",
            "skill points",
            "required sp",
            "required skill points",
            "required skill pts",
        ],
    )

    if value:
        match = re.search(r"\d+", value)

        if match:
            return match.group(0)

    patterns = [
        r"Skill cost\s*:?\s*(\d+)",
        r"Cost\s*:?\s*(\d+)",
        r"Skill points\s*:?\s*(\d+)",
        r"Required SP\s*:?\s*(\d+)",
        r"Required skill points\s*:?\s*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, detail_text, re.IGNORECASE)

        if match:
            return match.group(1)

    return ""


def parse_duration(detail_text):
    value = value_after_label(
        detail_text,
        [
            "base duration",
            "duration",
            "duration time",
        ],
    )

    if value:
        match = re.search(r"\d+(?:\.\d+)?\s*s", value, re.IGNORECASE)

        if match:
            return match.group(0).replace(" ", "")

    patterns = [
        r"Base duration\s*:?\s*(\d+(?:\.\d+)?\s*s)",
        r"Duration\s*:?\s*(\d+(?:\.\d+)?\s*s)",
    ]

    for pattern in patterns:
        match = re.search(pattern, detail_text, re.IGNORECASE)

        if match:
            return match.group(1).replace(" ", "")

    return ""


def parse_effect(detail_text, description):
    value = value_after_label(
        detail_text,
        [
            "effect",
            "effects",
        ],
    )

    if value and len(value) < 150:
        return value

    lines = get_lines(detail_text)

    effect_keywords = [
        "target speed",
        "current speed",
        "acceleration",
        "recover",
        "endurance",
        "speed",
        "stamina",
        "power",
        "guts",
        "wisdom",
        "decrease",
        "increase",
    ]

    for line in lines:
        low = line.lower()

        if any(keyword in low for keyword in effect_keywords):
            if re.search(r"\(\s*-?\d+(?:\.\d+)?\s*\)", line):
                return line

    for line in lines:
        low = line.lower()

        if "increase target speed" in low:
            return line

        if "increase acceleration" in low:
            return line

        if "recover endurance" in low:
            return line

        if "decrease target speed" in low:
            return line

    return guess_effect_from_description(description)


def guess_effect_from_description(description):
    low = description.lower()

    if "velocity" in low or "speed" in low:
        return "Increase target speed"

    if "acceleration" in low:
        return "Increase acceleration"

    if "recover" in low or "endurance" in low:
        return "Recover endurance"

    if "decrease" in low:
        return "Decrease performance"

    if "performance" in low:
        return "Increase performance"

    return ""


def guess_icon(icon_src, description, effect):
    if icon_src:
        filename = Path(urlparse(icon_src).path).name

        if filename:
            return filename

    text = f"{description} {effect}".lower()

    if "acceleration" in text:
        return "acceleration_skill.png"

    if "recover" in text or "endurance" in text or "stamina" in text:
        return "stamina_skill.png"

    if "velocity" in text or "target speed" in text or "speed" in text:
        return "speed_skill.png"

    return "skill.png"


def guess_rarity(name, detail_text):
    if "◎" in name:
        return "Upgraded"

    low = detail_text.lower()

    if "unique" in low:
        return "Unique"

    if "rare" in low:
        return "Rare"

    return "Normal"


def guess_type(name):
    if "◎" in name:
        return "upgrade"

    return "base"


def guess_parent_id(name):
    if "◎" not in name:
        return ""

    return slugify(remove_symbol(name))


def guess_category(description, effect):
    text = f"{description} {effect}".lower()

    if "decrease" in text or "impair" in text or "debuff" in text:
        return "debuff"

    if "recover" in text or "endurance" in text:
        return "recovery"

    return "buff"


def build_row(name, description, detail_text, icon_src):
    effect = parse_effect(detail_text, description)
    cost = parse_cost(detail_text)
    duration = parse_duration(detail_text)

    skill_type = guess_type(name)

    if skill_type == "upgrade":
        skill_points = ""
        required_sp = cost
    else:
        skill_points = cost
        required_sp = ""

    return {
        "id": slugify(name),
        "name": name,
        "icon": guess_icon(icon_src, description, effect),
        "rarity": guess_rarity(name, detail_text),
        "description": description,
        "effect": effect,
        "skill_points": skill_points,
        "type": skill_type,
        "parent_id": guess_parent_id(name),
        "required_sp": required_sp,
        "category": guess_category(description, effect),
        "base_duration": duration,
    }


def save_csv(rows):
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = []
    seen_ids = set()
    detail_debug_saved = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page(
            viewport={
                "width": 1366,
                "height": 900,
            }
        )

        print("Đang mở GameTora...")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)

        print("Title:", page.title())

        try:
            page.get_by_text("Detailed view", exact=True).click(timeout=3000)
            page.wait_for_timeout(1000)
            print("Đã bấm Detailed view")
        except Exception:
            print("Không bấm được Detailed view, bỏ qua")

        try:
            page.get_by_text("Always show all results", exact=True).click(timeout=3000)
            page.wait_for_timeout(3000)
            print("Đã bấm Always show all results")
        except Exception:
            print("Không bấm được Always show all results, bỏ qua")

        for scroll_round in range(120):
            print(f"Đang quét vòng scroll {scroll_round + 1}...")

            more_buttons = page.get_by_text("More", exact=True)
            more_count = more_buttons.count()

            print("Số nút More đang thấy:", more_count)

            for i in range(more_count):
                try:
                    more = more_buttons.nth(i)

                    card_data = get_card_data_from_more(more)
                    card_text = card_data["text"]
                    icon_src = card_data["icon"]

                    name, description = parse_card_text(card_text)

                    if not name or not description:
                        continue

                    skill_id = slugify(name)

                    if not skill_id:
                        continue

                    if skill_id in seen_ids:
                        continue

                    more.scroll_into_view_if_needed(timeout=3000)
                    page.wait_for_timeout(200)
                    more.click(timeout=3000)

                    detail_text = read_detail_text(page, name)

                    if not detail_debug_saved:
                        with open("detail_debug_first.txt", "w", encoding="utf-8") as f:
                            f.write(detail_text)
                        detail_debug_saved = True

                    close_popup(page)

                    row = build_row(name, description, detail_text, icon_src)

                    rows.append(row)
                    seen_ids.add(skill_id)

                    print(
                        f"{len(rows)}. {row['id']} | "
                        f"effect={row['effect']} | "
                        f"sp={row['skill_points'] or row['required_sp']} | "
                        f"duration={row['base_duration']}"
                    )

                    save_csv(rows)

                except Exception as error:
                    print("Bỏ qua 1 skill vì lỗi:", error)
                    close_popup(page)

            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(600)

        browser.close()

    save_csv(rows)

    print("=" * 60)
    print(f"Xong. Đã lưu {len(rows)} dòng vào {OUTPUT}")
    print("File debug chi tiết đầu tiên: detail_debug_first.txt")
    print("=" * 60)


if __name__ == "__main__":
    main()