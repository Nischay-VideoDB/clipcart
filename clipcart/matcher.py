"""Match a product to its on-screen window via spoken-word search,
with optional Kimi vision verification to confirm the right shot.
"""

import logging
from typing import Any

from openai import OpenAI

from clipcart.video import search_spoken
from clipcart.image_verify import get_video_frame_url, verify_frame_match

logger = logging.getLogger(__name__)

# POC: window is inferred from spoken-word search + optional image verification.
# production: seed start/end from real sale_timestamp in Shopee order data.


def find_product_window(
    video: Any,
    product: dict[str, Any],
    min_len: float,
    max_len: float,
    lead: float,
    kimi_client: OpenAI | None = None,
) -> tuple[float, float] | None:
    """Locate a product's on-screen window via spoken-word search.

    Picks the top shot for the product name, starts a little before it,
    and clamps the window to [min_len, max_len] seconds.

    When the product has an ``image_url`` and ``kimi_client`` is provided,
    runs a secondary image similarity check against the top candidate frames
    to confirm the right shot is selected.

    Falls back to a shorter keyword (first word of the name) if the full
    name returns no shots.

    Args:
        video: An indexed VideoDB Video object.
        product: A dict with ``name`` and optionally ``image_url``.
        min_len: Minimum clip length in seconds.
        max_len: Maximum clip length in seconds.
        lead: Seconds to start before the matched mention.
        kimi_client: Optional Kimi OpenAI client for image verification.

    Returns:
        tuple[float, float] | None: (start, end) seconds, or None if no match.
    """
    name = product["name"]
    shots = search_spoken(video, name)

    if not shots:
        keyword = _first_keyword(name)
        if keyword != name:
            logger.warning("No shots for %r — retrying with keyword %r", name, keyword)
            shots = search_spoken(video, keyword)

    if not shots:
        logger.warning("No spoken match found for product %r — skipping.", name)
        return None

    best_shot = _pick_best_shot(video, product, shots, kimi_client)

    start = max(0.0, best_shot.start - lead)
    end = max(best_shot.end, start + min_len)
    if (end - start) > max_len:
        end = start + max_len
    # Provider clips may be shorter than the desired window. VideoDB rejects an
    # end timestamp beyond the real source duration, so clamp and backfill the
    # start while preserving as much context as the source actually contains.
    try:
        duration = float(getattr(video, "length", 0) or 0)
    except (TypeError, ValueError):
        duration = 0
    if duration > 0 and end > duration:
        end = duration
        start = max(0.0, min(start, end - min(min_len, end)))
    if end <= start:
        logger.warning("Matched window for %r is outside the source duration — skipping.", name)
        return None

    logger.info(
        "Matched %r -> window %.1fs–%.1fs (%.1fs)",
        name, start, end, end - start,
    )
    return (start, end)


def _pick_best_shot(
    video: Any,
    product: dict[str, Any],
    shots: list[Any],
    kimi_client: OpenAI | None,
) -> Any:
    """Select the best shot from candidates, using image verification if available.

    Without a Kimi client or product image, returns the top-ranked shot.
    With both, checks up to the top 3 shots and returns the first confirmed match.

    Args:
        video: An indexed VideoDB Video object.
        product: Product dict with optional ``image_url``.
        shots: Ranked list of shot objects from spoken-word search.
        kimi_client: Optional Kimi client for image verification.

    Returns:
        The selected shot object.
    """
    image_url = product.get("image_url")

    if not kimi_client or not image_url:
        return shots[0]

    # check up to top 3 candidates with image verification
    for shot in shots[:3]:
        mid = (shot.start + shot.end) / 2
        frame_url = get_video_frame_url(video, mid)
        if not frame_url:
            logger.debug("No frame URL for shot at %.1fs — skipping image verify.", mid)
            continue

        if verify_frame_match(kimi_client, image_url, frame_url):
            logger.info("Image verification confirmed shot at %.1fs–%.1fs.", shot.start, shot.end)
            return shot

    logger.warning(
        "Image verification found no confirmed shot for %r — using top spoken match.",
        product["name"],
    )
    return shots[0]


def _first_keyword(name: str) -> str:
    """Extract the first meaningful word from a product name.

    Args:
        name: Full product name string.

    Returns:
        str: The first keyword, or the original name if none found.
    """
    skip = {"the", "a", "an", "of", "for", "with"}
    for word in name.split():
        if word.lower() not in skip and len(word) > 2:
            return word
    return name
