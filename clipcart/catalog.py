"""Catalog loading: Bright Data scrape (optional) with cached JSON fallback."""

import json
import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def load_catalog(
    path: str,
    token: str | None = None,
    url: str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Return a list of product dicts for the POC.

    Tries a live Bright Data scrape when ``token`` and ``url`` are given,
    otherwise loads the cached JSON at ``path``. Always falls back to cached
    data if scraping fails, so the demo never blocks.

    Args:
        path: Path to the cached catalog JSON (fallback + default).
        token: Bright Data API token, or None to skip scraping.
        url: Shopee shop/live page to scrape, or None to skip scraping.
        limit: Max number of products to return.

    Returns:
        list[dict]: Products with keys ``name``, ``price``, ``buy_url``, ``image_url``.
    """
    if token and url:
        try:
            products = _scrape_brightdata(token, url)
            if products:
                logger.info("Loaded %d products from Bright Data scrape.", len(products))
                return products[:limit]
        except Exception as exc:
            logger.warning("Bright Data scrape failed (%s) — falling back to cached catalog.", exc)

    return _load_cached(path, limit)


def _scrape_brightdata(token: str, url: str) -> list[dict[str, Any]]:
    """Scrape a Shopee page via Bright Data Web Unlocker.

    Args:
        token: Bright Data API bearer token.
        url: Target URL to scrape.

    Returns:
        list[dict]: Parsed product list.
    """
    resp = requests.post(
        "https://api.brightdata.com/request",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"zone": "web_unlocker", "url": url, "format": "raw"},
        timeout=30,
    )
    resp.raise_for_status()
    return _parse_html_products(resp.text)


def _parse_html_products(html: str) -> list[dict[str, Any]]:
    """Parse product data from raw Shopee HTML.

    Args:
        html: Raw HTML string from Bright Data.

    Returns:
        list[dict]: Extracted products. Returns empty list if parsing fails.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    products: list[dict[str, Any]] = []

    for item in soup.select("[data-sqe='item']"):
        name_el = item.select_one("[data-sqe='name']")
        price_el = item.select_one("[data-sqe='price']")
        link_el = item.select_one("a")
        img_el = item.select_one("img")

        if not (name_el and price_el):
            continue

        products.append({
            "name": name_el.get_text(strip=True),
            "price": price_el.get_text(strip=True),
            "buy_url": link_el["href"] if link_el else "",
            "image_url": img_el["src"] if img_el else "",
        })

    return products


def _load_cached(path: str, limit: int) -> list[dict[str, Any]]:
    """Load products from a local JSON file.

    Args:
        path: Path to the JSON catalog file.
        limit: Max number of products to return.

    Returns:
        list[dict]: Product list.

    Raises:
        FileNotFoundError: If the catalog file does not exist.
    """
    catalog_path = Path(path)
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog file not found: {path}")
    with catalog_path.open() as f:
        products = json.load(f)
    logger.info("Loaded %d products from cached catalog: %s", len(products), path)
    return products[:limit]


def from_shopee_api(shop_id: str, token: str) -> list[dict[str, Any]]:
    """Load catalog from the Shopee Open Platform API.

    Args:
        shop_id: Seller's Shopee shop ID.
        token: OAuth access token.

    Returns:
        list[dict]: Product list.

    Raises:
        NotImplementedError: Always — production path not implemented in POC.
    """
    # production: pulls catalog + real order timeline via Shopee Open Platform (OAuth)
    raise NotImplementedError("production: seller connects Shopee account")
