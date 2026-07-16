"""
Crawl toàn bộ item từ:
https://gametora.com/umamusume/items

Kết quả:
- data/items.csv
- data/items.json
- static/images/items/*.png|webp|jpg

Cài đặt:
    pip install playwright
    playwright install chromium

Chạy:
    python crawl_gametora_items.py
"""

from __future__ import annotations

import csv
import json
import mimetypes
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


PAGE_URL = "https://gametora.com/umamusume/items"

CSV_PATH = Path("data/items.csv")
JSON_PATH = Path("data/items.json")
IMAGE_DIR = Path("static/images/items")
DEBUG_DIR = Path("debug_items_crawl")

HEADLESS = True
PAGE_TIMEOUT_MS = 90_000
REQUEST_DELAY_SECONDS = 0.05


def clean_text(value: Any) -> str:
    """Chuẩn hóa khoảng trắng và loại bỏ ký tự thừa."""
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slugify(value: str) -> str:
    """Đổi tên item thành slug dùng cho id và tên ảnh."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "_", ascii_text)
    ascii_text = re.sub(r"_+", "_", ascii_text)
    return ascii_text.strip("_") or "item"


def ensure_directories() -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def dismiss_cookie_or_popup(page: Page) -> None:
    """Đóng cookie/popup nếu trang hiện ra."""
    button_texts = [
        "Accept",
        "Accept all",
        "I agree",
        "Agree",
        "Got it",
        "Close",
        "OK",
    ]

    for text in button_texts:
        try:
            locator = page.get_by_role("button", name=re.compile(rf"^{re.escape(text)}$", re.I))
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click(timeout=1_500)
        except Exception:
            pass


def reset_filters(page: Page) -> None:
    """Đưa trang về bộ lọc Any để tránh bỏ sót item."""
    candidates = [
        page.get_by_text("Reset filters", exact=False),
        page.locator("text=/Reset filters/i"),
    ]

    for locator in candidates:
        try:
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click(timeout=3_000)
                page.wait_for_timeout(700)
                break
        except Exception:
            pass

    # Bật hiển thị ID/cap nếu trang hỗ trợ. Không bắt buộc để crawl thành công.
    try:
        label = page.get_by_text("Show item IDs and caps", exact=False)
        if label.count() > 0 and label.first.is_visible():
            label.first.click(timeout=2_000)
            page.wait_for_timeout(500)
    except Exception:
        pass


def scroll_until_stable(page: Page) -> None:
    """Cuộn hết trang để nạp toàn bộ item và ảnh lazy-load."""
    previous_height = 0
    stable_rounds = 0

    for _ in range(80):
        current_height = page.evaluate("document.documentElement.scrollHeight")

        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(350)

        new_height = page.evaluate("document.documentElement.scrollHeight")

        if new_height == previous_height == current_height:
            stable_rounds += 1
        else:
            stable_rounds = 0

        previous_height = new_height

        if stable_rounds >= 4:
            break

    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)


def extract_items_from_dom(page: Page) -> list[dict[str, Any]]:
    """
    Đọc item bằng cấu trúc nội dung thay vì phụ thuộc hoàn toàn vào tên class.
    Cách này ít bị hỏng hơn khi GameTora đổi tên CSS class.
    """
    javascript = r"""
    () => {
        const normalize = (value) =>
            (value || "")
                .replace(/\u00a0/g, " ")
                .replace(/\s+/g, " ")
                .trim();

        const ownText = (element) =>
            normalize(
                Array.from(element.childNodes)
                    .filter((node) => node.nodeType === Node.TEXT_NODE)
                    .map((node) => node.textContent || "")
                    .join(" ")
            );

        const containsLabel = (element, pattern) => {
            const direct = ownText(element);
            const total = normalize(element.textContent);
            return pattern.test(direct) || pattern.test(total);
        };

        const allElements = Array.from(document.querySelectorAll("body *"));

        const usesLabels = allElements.filter((element) => {
            const direct = ownText(element);
            return /^uses\s*:?\s*$/i.test(direct);
        });

        const howLabels = allElements.filter((element) => {
            const direct = ownText(element);
            return /^how\s+to\s+get\s*:?\s*$/i.test(direct);
        });

        const labelCandidates = [...usesLabels, ...howLabels];
        const cardSet = new Set();

        function relevantImages(element) {
            return Array.from(element.querySelectorAll("img")).filter((img) => {
                const source = img.currentSrc || img.src || img.dataset.src || "";
                const alt = normalize(img.alt);
                return (
                    /\/items?\//i.test(source) ||
                    /item/i.test(source) ||
                    (alt && !/logo|header|banner|character rate up|support rate up/i.test(alt))
                );
            });
        }

        function findSmallestCard(label) {
            let current = label;

            while (current && current !== document.body) {
                const text = normalize(current.innerText);
                const hasUses = /\buses\s*:/i.test(text);
                const hasHow = /\bhow\s+to\s+get\s*:/i.test(text);
                const images = relevantImages(current);

                if (hasUses && hasHow && images.length > 0) {
                    return current;
                }

                current = current.parentElement;
            }

            return null;
        }

        for (const label of labelCandidates) {
            const card = findSmallestCard(label);
            if (card) {
                cardSet.add(card);
            }
        }

        function findExactLabel(card, regex) {
            return Array.from(card.querySelectorAll("*")).find((element) => {
                return regex.test(ownText(element));
            }) || null;
        }

        function firstListAfter(label, card, stopLabel = null) {
            if (!label) return [];

            const lists = Array.from(card.querySelectorAll("ul, ol"));

            for (const list of lists) {
                const relation = label.compareDocumentPosition(list);
                const followsLabel = Boolean(relation & Node.DOCUMENT_POSITION_FOLLOWING);

                if (!followsLabel) continue;

                if (stopLabel) {
                    const stopRelation = stopLabel.compareDocumentPosition(list);
                    const listAfterStop = Boolean(
                        stopRelation & Node.DOCUMENT_POSITION_FOLLOWING
                    );

                    if (listAfterStop) continue;
                }

                const values = Array.from(list.querySelectorAll(":scope > li"))
                    .map((li) => normalize(li.innerText))
                    .filter(Boolean);

                if (values.length > 0) {
                    return values;
                }
            }

            // Fallback khi dữ liệu không nằm trong ul/li.
            let current = label.nextElementSibling;
            const values = [];

            while (current && current !== stopLabel) {
                if (/^(uses|how\s+to\s+get)\s*:?$/i.test(ownText(current))) {
                    break;
                }

                const text = normalize(current.innerText);
                if (text) values.push(text);

                current = current.nextElementSibling;
            }

            return values;
        }

        function findName(card, image) {
            const headings = Array.from(
                card.querySelectorAll("h1, h2, h3, h4, h5, h6")
            )
                .map((element) => normalize(element.innerText))
                .filter((text) =>
                    text &&
                    !/^(uses|how\s+to\s+get)\s*:?$/i.test(text)
                );

            if (headings.length > 0) {
                return headings[0];
            }

            const alt = normalize(image?.alt);
            if (
                alt &&
                !/^(image|item|icon)$/i.test(alt) &&
                !/logo|header|banner/i.test(alt)
            ) {
                return alt;
            }

            // Tìm đoạn chữ ngắn gần ảnh.
            const textCandidates = Array.from(card.querySelectorAll("div, span, p"))
                .map((element) => normalize(element.innerText))
                .filter((text) =>
                    text &&
                    text.length <= 100 &&
                    !/^(uses|how\s+to\s+get)\s*:?$/i.test(text) &&
                    !text.includes("Used to") &&
                    !text.includes("Bought in")
                );

            return textCandidates[0] || "";
        }

        function findDescription(card, usesLabel, name) {
            const italic = card.querySelector("em, i");
            if (italic) {
                const text = normalize(italic.innerText);
                if (text && text !== name) return text;
            }

            const paragraphs = Array.from(card.querySelectorAll("p"));

            for (const paragraph of paragraphs) {
                if (usesLabel) {
                    const relation = paragraph.compareDocumentPosition(usesLabel);
                    const paragraphBeforeUses = Boolean(
                        relation & Node.DOCUMENT_POSITION_FOLLOWING
                    );

                    if (!paragraphBeforeUses) continue;
                }

                const text = normalize(paragraph.innerText);

                if (
                    text &&
                    text !== name &&
                    !/^(uses|how\s+to\s+get)\s*:?$/i.test(text)
                ) {
                    return text;
                }
            }

            return "";
        }

        const results = [];

        for (const card of cardSet) {
            const images = relevantImages(card);
            const image = images[0] || card.querySelector("img");

            const usesLabel = findExactLabel(card, /^uses\s*:?\s*$/i);
            const howLabel = findExactLabel(card, /^how\s+to\s+get\s*:?\s*$/i);

            const name = findName(card, image);
            const description = findDescription(card, usesLabel, name);
            const uses = firstListAfter(usesLabel, card, howLabel);
            const howToGet = firstListAfter(howLabel, card, null);

            const imageUrl =
                image?.currentSrc ||
                image?.src ||
                image?.dataset?.src ||
                image?.getAttribute("data-src") ||
                "";

            const cardText = normalize(card.innerText);

            const gameIdMatch =
                cardText.match(/\b(?:item\s*)?id\s*:?\s*(\d{2,})\b/i) ||
                imageUrl.match(/(?:^|\/)(\d{2,})(?:[._-]|$)/);

            const capMatch = cardText.match(/\bcap\s*:?\s*([^|,;]+)/i);

            // Một số phiên bản trang có badge/type trong card.
            const badges = Array.from(
                card.querySelectorAll(
                    "[class*='badge'], [class*='type'], [data-item-type]"
                )
            )
                .map((element) =>
                    normalize(
                        element.getAttribute("data-item-type") ||
                        element.innerText
                    )
                )
                .filter(Boolean)
                .filter((value) =>
                    value !== name &&
                    !/^(uses|how\s+to\s+get)\s*:?$/i.test(value)
                );

            results.push({
                name,
                description,
                uses,
                how_to_get: howToGet,
                image_url: imageUrl,
                game_id: gameIdMatch ? gameIdMatch[1] : "",
                cap: capMatch ? normalize(capMatch[1]) : "",
                item_type: badges[0] || "",
                raw_text: cardText,
            });
        }

        return results;
    }
    """

    raw_items = page.evaluate(javascript)

    items: list[dict[str, Any]] = []

    for raw in raw_items:
        name = clean_text(raw.get("name"))
        if not name:
            continue

        uses = [
            clean_text(value)
            for value in raw.get("uses", [])
            if clean_text(value)
        ]

        how_to_get = [
            clean_text(value)
            for value in raw.get("how_to_get", [])
            if clean_text(value)
        ]

        items.append(
            {
                "name": name,
                "description": clean_text(raw.get("description")),
                "uses": uses,
                "how_to_get": how_to_get,
                "image_url": clean_text(raw.get("image_url")),
                "game_id": clean_text(raw.get("game_id")),
                "cap": clean_text(raw.get("cap")),
                "item_type": clean_text(raw.get("item_type")),
                "raw_text": clean_text(raw.get("raw_text")),
            }
        )

    return items


def deduplicate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Loại item bị đọc trùng do DOM có phiên bản desktop/mobile."""
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in items:
        key = (
            item["name"].casefold(),
            item.get("game_id", "") or item.get("image_url", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def extension_from_response(
    image_url: str,
    content_type: str,
) -> str:
    """Xác định đuôi file ảnh."""
    parsed_suffix = Path(unquote(urlparse(image_url).path)).suffix.lower()

    if parsed_suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}:
        return ".jpg" if parsed_suffix == ".jpeg" else parsed_suffix

    clean_content_type = content_type.split(";")[0].strip().lower()
    guessed = mimetypes.guess_extension(clean_content_type) or ".png"

    if guessed == ".jpe":
        guessed = ".jpg"

    return guessed


def download_image(
    context: BrowserContext,
    image_url: str,
    destination_stem: Path,
) -> str:
    """Tải một ảnh bằng request context của Playwright."""
    if not image_url or image_url.startswith("data:"):
        return ""

    absolute_url = urljoin(PAGE_URL, image_url)

    try:
        response = context.request.get(
            absolute_url,
            headers={"Referer": PAGE_URL},
            timeout=45_000,
        )

        if not response.ok:
            print(
                f"  [ẢNH LỖI {response.status}] {absolute_url}",
                file=sys.stderr,
            )
            return ""

        content_type = response.headers.get("content-type", "")
        extension = extension_from_response(absolute_url, content_type)
        destination = destination_stem.with_suffix(extension)

        destination.write_bytes(response.body())
        return destination.name

    except Exception as error:
        print(f"  [ẢNH LỖI] {absolute_url}: {error}", file=sys.stderr)
        return ""


def assign_ids_and_download_images(
    context: BrowserContext,
    items: list[dict[str, Any]],
) -> None:
    """Tạo slug/id duy nhất và tải ảnh về thư mục static."""
    used_ids: set[str] = set()

    for index, item in enumerate(items, start=1):
        base_id = slugify(item["name"])

        if base_id in used_ids:
            suffix = item.get("game_id") or str(index)
            item_id = f"{base_id}_{suffix}"
        else:
            item_id = base_id

        used_ids.add(item_id)
        item["id"] = item_id

        print(f"[{index}/{len(items)}] {item['name']}")

        image_filename = download_image(
            context=context,
            image_url=item.get("image_url", ""),
            destination_stem=IMAGE_DIR / item_id,
        )

        item["image"] = image_filename
        time.sleep(REQUEST_DELAY_SECONDS)


def save_csv(items: list[dict[str, Any]]) -> None:
    """Lưu CSV dùng dấu | để ngăn nhiều dòng."""
    fieldnames = [
        "id",
        "name",
        "image",
        "description",
        "uses",
        "how_to_get",
        "item_type",
        "game_id",
        "cap",
        "source_url",
        "source_image_url",
    ]

    with CSV_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for item in items:
            writer.writerow(
                {
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "image": item.get("image", ""),
                    "description": item.get("description", ""),
                    "uses": "|".join(item.get("uses", [])),
                    "how_to_get": "|".join(item.get("how_to_get", [])),
                    "item_type": item.get("item_type", ""),
                    "game_id": item.get("game_id", ""),
                    "cap": item.get("cap", ""),
                    "source_url": PAGE_URL,
                    "source_image_url": item.get("image_url", ""),
                }
            )


def save_json(items: list[dict[str, Any]]) -> None:
    """Lưu thêm JSON để kiểm tra dữ liệu dễ hơn."""
    serializable_items = []

    for item in items:
        serializable_items.append(
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "image": item.get("image", ""),
                "description": item.get("description", ""),
                "uses": item.get("uses", []),
                "how_to_get": item.get("how_to_get", []),
                "item_type": item.get("item_type", ""),
                "game_id": item.get("game_id", ""),
                "cap": item.get("cap", ""),
                "source_url": PAGE_URL,
                "source_image_url": item.get("image_url", ""),
            }
        )

    JSON_PATH.write_text(
        json.dumps(serializable_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_debug_files(page: Page) -> None:
    """Lưu HTML và ảnh chụp để xem khi selector không đọc được."""
    try:
        (DEBUG_DIR / "items_page.html").write_text(
            page.content(),
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        page.screenshot(
            path=str(DEBUG_DIR / "items_page.png"),
            full_page=True,
        )
    except Exception:
        pass


def main() -> None:
    ensure_directories()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            print(f"Đang mở: {PAGE_URL}")
            page.goto(
                PAGE_URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )

            try:
                page.wait_for_load_state(
                    "networkidle",
                    timeout=30_000,
                )
            except PlaywrightTimeoutError:
                # Một số trang luôn có request nền nên networkidle có thể timeout.
                pass

            dismiss_cookie_or_popup(page)
            reset_filters(page)
            scroll_until_stable(page)

            items = extract_items_from_dom(page)
            items = deduplicate_items(items)

            if not items:
                save_debug_files(page)
                raise RuntimeError(
                    "Không đọc được item nào. "
                    "Hãy mở debug_items_crawl/items_page.png và "
                    "debug_items_crawl/items_page.html để kiểm tra giao diện mới."
                )

            print(f"\nTìm thấy {len(items)} item.")
            assign_ids_and_download_images(context, items)

            save_csv(items)
            save_json(items)

            print("\nCrawl hoàn tất:")
            print(f"- CSV:  {CSV_PATH.resolve()}")
            print(f"- JSON: {JSON_PATH.resolve()}")
            print(f"- Ảnh:  {IMAGE_DIR.resolve()}")

        except Exception:
            save_debug_files(page)
            raise

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
