"""Scrape product catalog from thestylesoiree.sg and write catalog JSON.

The site is on Shopcada. Product cards are div.productrow elements containing
name (img alt), price (text "SGD X.XX"), image (img[data-src]), and URL (a.ga_track).

Usage:
    uv run python scripts/scrape_catalog.py
    uv run python scripts/scrape_catalog.py --url https://www.thestylesoiree.sg/products --limit 10
    uv run python scripts/scrape_catalog.py --search "Pyonie Puffy Sleeve"
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.thestylesoiree.sg"
DEFAULT_LISTING_URL = f"{BASE_URL}/products?items_per_page=all"
DEFAULT_OUT = "data/catalog.sample.json"
DEFAULT_LIMIT = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch_page(url: str) -> BeautifulSoup:
    """Fetch a page and return a BeautifulSoup object.

    Args:
        url: Page URL to fetch.

    Returns:
        BeautifulSoup: Parsed HTML.

    Raises:
        requests.HTTPError: On non-2xx response.
    """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    logger.info("Fetched %s (%d bytes)", url, len(resp.text))
    return BeautifulSoup(resp.text, "html.parser")


def parse_product_rows(soup: BeautifulSoup) -> list[dict]:
    """Extract all products from a page containing div.productrow cards.

    Args:
        soup: Parsed page HTML.

    Returns:
        list[dict]: Products with name, price, buy_url, image_url.
    """
    rows = soup.select("div.productrow")
    logger.info("Found %d product rows on page.", len(rows))
    products = []
    for row in rows:
        product = _parse_row(row)
        if product:
            products.append(product)
    return products


def _parse_row(row: BeautifulSoup) -> dict | None:
    """Parse one div.productrow into a product dict.

    Args:
        row: A BeautifulSoup Tag for a single productrow div.

    Returns:
        dict | None: Product dict, or None if required fields are missing.
    """
    # name from img alt or link title
    img = row.select_one("img[alt]")
    name = img["alt"].strip() if img else None
    if not name:
        link = row.select_one("a.ga_track")
        name = link.get("title", "").strip() if link else None
    if not name:
        return None

    # product URL
    link = row.select_one("a.ga_track[href]")
    buy_url = link["href"] if link else BASE_URL
    if buy_url and not buy_url.startswith("http"):
        buy_url = BASE_URL + buy_url

    # image — use data-src for lazy-loaded images, fall back to src
    image_url = ""
    if img:
        image_url = img.get("data-src") or img.get("src") or ""
        # skip the SVG placeholder
        if "svg+xml" in image_url:
            image_url = img.get("data-src", "")

    # price — look for "SGD X.XX" pattern in the card text
    text = row.get_text(" ", strip=True)
    price_match = re.search(r"SGD\s*([\d,]+\.?\d*)", text)
    price = f"SGD {price_match.group(1)}" if price_match else ""

    return {
        "name": name,
        "price": price,
        "buy_url": buy_url,
        "image_url": image_url,
    }


def scrape_products(listing_url: str, limit: int, keyword: str | None = None) -> list[dict]:
    """Scrape product listings from one or more pages.

    If keyword is set, tries the site search URL first.
    Otherwise scrapes the listing page and follows pagination up to limit.

    Args:
        listing_url: Base product listing or search URL.
        limit: Max products to return.
        keyword: Optional search keyword to filter products.

    Returns:
        list[dict]: Scraped products up to limit.
    """
    soup = fetch_page(listing_url)
    all_products = parse_product_rows(soup)
    logger.info("Fetched %d products total.", len(all_products))

    if keyword:
        kw_lower = keyword.lower()
        words = [w for w in keyword.split() if len(w) > 3]
        filtered = [
            p for p in all_products
            if kw_lower in p["name"].lower()
            or all(w.lower() in p["name"].lower() for w in words)
        ]
        logger.info("Keyword %r matched %d products.", keyword, len(filtered))
        return filtered[:limit]

    return all_products[:limit]


def main() -> None:
    """Parse args, scrape, write catalog JSON."""
    parser = argparse.ArgumentParser(description="Scrape thestylesoiree.sg and write catalog JSON.")
    parser.add_argument("--url", default=DEFAULT_LISTING_URL, help="Product listing URL.")
    parser.add_argument("--search", default=None, help="Optional keyword to search for.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    products = scrape_products(args.url, args.limit, keyword=args.search)

    if not products:
        logger.error("No products found.")
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %d products to %s", len(products), out_path)
    for p in products:
        logger.info("  - %s (%s)", p["name"], p["price"])


if __name__ == "__main__":
    main()
