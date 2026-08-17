"""Generate short-form shopping copy (hook, caption, hashtags) via Kimi K2."""

import json
import logging
from typing import Any

from openai import OpenAI

from clipcart.config import get_env

logger = logging.getLogger(__name__)

# Edit this prompt to tune Kimi's output style and format.
SYSTEM_PROMPT = (
    "You are a short-form e-commerce copywriter for live-selling videos. "
    "Write punchy, engaging copy that drives clicks. "
    "Return STRICT JSON only — no markdown, no extra keys:\n"
    '{"hook": str, "caption": str, "hashtags": [str], "post_offset_hours": int}\n\n'
    "Rules:\n"
    "- hook: one attention-grabbing sentence (max 15 words) to open the clip\n"
    "- caption: 2-3 sentences describing the product and deal\n"
    "- hashtags: 5-8 relevant hashtags without the # symbol\n"
    "- post_offset_hours: suggested hours after recording to post (0, 1, 6, 12, or 24)"
)

_FALLBACK_COPY = {
    "hook": "",
    "caption": "",
    "hashtags": [],
    "post_offset_hours": 24,
}


def make_client() -> OpenAI | None:
    """Create an OpenAI client pointed at the Moonshot (Kimi) API.

    Returns:
        OpenAI: A configured client for the Moonshot base URL.
    """
    api_key = get_env("MOONSHOT_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.moonshot.ai/v1")


def write_copy(
    client: OpenAI | None,
    product: dict[str, Any],
    transcript: str,
) -> dict[str, Any]:
    """Generate hook/caption/hashtags/post offset for one clip via Kimi.

    Args:
        client: An OpenAI client pointed at the Moonshot base URL.
        product: A dict with ``name`` and ``price``.
        transcript: The spoken text within the clip window.

    Returns:
        dict: Parsed JSON copy with keys hook, caption, hashtags, post_offset_hours.
              Falls back to a basic dict on any error.
    """
    user_message = (
        f"Product name: {product['name']}\n"
        f"Price: {product['price']}\n"
        f"Transcript from the clip: {transcript or '(no transcript available)'}"
    )

    if client is None:
        fallback = dict(_FALLBACK_COPY)
        fallback["hook"] = product["name"]
        fallback["caption"] = f"Check out {product['name']} for {product['price']}."
        return fallback

    try:
        resp = client.chat.completions.create(
            model="kimi-k2.6",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        copy = json.loads(resp.choices[0].message.content)
        logger.info("Generated copy for %r: hook=%r", product["name"], copy.get("hook"))
        return copy

    except Exception as exc:
        logger.warning("Kimi copy generation failed for %r (%s) — using fallback.", product["name"], exc)
        fallback = dict(_FALLBACK_COPY)
        fallback["hook"] = product["name"]
        fallback["caption"] = f"Check out {product['name']} for only {product['price']}!"
        return fallback
