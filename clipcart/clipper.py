"""Build shoppable clips using VideoDB Timeline: trim + overlay + captions."""

import logging
from typing import Any

from videodb.timeline import Timeline
from videodb.asset import VideoAsset

logger = logging.getLogger(__name__)


def build_clip(
    conn: Any,
    video: Any,
    window: tuple[float, float],
    product: dict[str, Any],
) -> str:
    """Render a shoppable clip: trim + auto captions (no burned-in overlay).

    Price and buy URL are kept in clips.json for the UI to display.

    Args:
        conn: An authenticated VideoDB connection.
        video: The indexed source Video object.
        window: (start, end) in seconds.
        product: A dict with ``price`` and ``buy_url`` keys.

    Returns:
        str: An HLS stream URL for the rendered clip.
    """
    start, end = window
    duration = end - start

    tl = Timeline(conn)
    tl.add_inline(VideoAsset(asset_id=video.id, start=start, end=end))
    _add_captions(tl, video, start, end)

    stream_url = tl.generate_stream()
    logger.info(
        "Built clip for %r: %.1fs–%.1fs",
        product["name"], start, end,
    )
    return stream_url


def _add_captions(tl: Timeline, video: Any, start: float, end: float) -> None:
    """Attach auto-captions to the timeline if the index supports it.

    Silently skips if CaptionAsset is unavailable or the call fails,
    since captions are a nice-to-have and should not block clip generation.

    Args:
        tl: The Timeline being built.
        video: The indexed source Video (must have spoken-word index).
        start: Clip start time in seconds.
        end: Clip end time in seconds.
    """
    try:
        from videodb.asset import CaptionAsset
        tl.add_overlay(0, CaptionAsset(src="auto"))
    except Exception as exc:
        logger.warning("Captions unavailable — skipping (%s).", exc)
