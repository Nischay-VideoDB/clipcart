"""Orchestrate the full ClipCart pipeline: catalog -> match -> clip -> copy -> JSON."""

import json
import logging
import os
from typing import Any

from clipcart import config
from clipcart.catalog import load_catalog
from clipcart.video import connect, get_or_upload, search_spoken
from clipcart.matcher import find_product_window
from clipcart.clipper import build_clip
from clipcart.copywriter import make_client, write_copy

logger = logging.getLogger(__name__)


def run(
    video_source: str,
    catalog_path: str = config.SAMPLE_CATALOG_PATH,
    limit: int = config.DEFAULT_LIMIT,
    out_path: str = "output/clips.json",
    use_image_verify: bool = True,
) -> list[dict[str, Any]]:
    """Run the full POC pipeline and write the gallery JSON.

    Steps: load catalog -> upload+index video -> for each product,
    match window -> build clip -> generate copy -> assemble record.
    Products with no spoken-word match are skipped.

    Args:
        video_source: URL or local file path to the source video.
        catalog_path: Path to the product catalog JSON.
        limit: Max number of products to process.
        out_path: Output path for the clips JSON file.
        use_image_verify: Whether to use Kimi vision to verify shot selection.

    Returns:
        list[dict]: The clip records written to ``out_path``.
    """
    kimi_client = make_client()

    logger.info("Loading catalog from %s (limit=%d)...", catalog_path, limit)
    products = load_catalog(
        path=catalog_path,
        token=config.get_env("BRIGHTDATA_API_TOKEN"),
        limit=limit,
    )
    logger.info("Loaded %d products.", len(products))

    logger.info("Connecting to VideoDB...")
    conn = connect()

    logger.info("Uploading and indexing video: %s", video_source)
    video = get_or_upload(conn, video_source)

    clips: list[dict[str, Any]] = []

    for i, product in enumerate(products, 1):
        print(f"[{i}/{len(products)}] Processing: {product['name']}")

        window = find_product_window(
            video=video,
            product=product,
            min_len=config.MIN_CLIP_LEN,
            max_len=config.MAX_CLIP_LEN,
            lead=config.LEAD_SECONDS,
            kimi_client=kimi_client if use_image_verify else None,
        )

        if window is None:
            print(f"  -> No match found — skipped.")
            continue

        stream_url = build_clip(conn, video, window, product)

        transcript = _get_transcript(video, window)
        copy = write_copy(kimi_client, product, transcript)

        record = {
            "name": product["name"],
            "price": product["price"],
            "buy_url": product["buy_url"],
            "image_url": product.get("image_url", ""),
            "hook": copy.get("hook", ""),
            "caption": copy.get("caption", ""),
            "hashtags": copy.get("hashtags", []),
            "schedule": copy.get("post_offset_hours", 24),
            "stream_url": stream_url,
            "start": window[0],
            "end": window[1],
        }
        clips.append(record)
        print(f"  -> Done. Hook: {record['hook']!r}")

    _write_output(clips, out_path)
    print(f"\nWrote {len(clips)} clip(s) to {out_path}")
    return clips


def _get_transcript(video: Any, window: tuple[float, float]) -> str:
    """Extract spoken text within a clip window from the video transcript.

    Uses video.get_transcript() to fetch the full word-level transcript,
    then filters words that fall within the window.

    Args:
        video: An indexed VideoDB Video object.
        window: (start, end) in seconds.

    Returns:
        str: Spoken text within the window, or empty string if unavailable.
    """
    start, end = window
    try:
        transcript = video.get_transcript()
        if not transcript:
            return ""
        # transcript is a list of word dicts with 'start', 'end', 'word' keys
        words = [
            w.get("word", w.get("text", ""))
            for w in transcript
            if w.get("start", 0) >= start and w.get("end", 0) <= end
        ]
        return " ".join(words).strip()
    except Exception as exc:
        logger.warning("Could not extract transcript for window %.1f–%.1f: %s", start, end, exc)
        return ""


def _write_output(clips: list[dict[str, Any]], out_path: str) -> None:
    """Write clip records to a pretty-printed JSON file.

    Args:
        clips: List of clip record dicts.
        out_path: Destination file path.
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clips, f, indent=2, ensure_ascii=False)
