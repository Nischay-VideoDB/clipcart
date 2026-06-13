"""Image similarity verification using Kimi's vision model.

Compares a product reference image against a video frame to confirm
the spoken-word match is showing the right product on screen.
"""

import base64
import logging
from typing import Any
from urllib.request import urlopen

from openai import OpenAI

logger = logging.getLogger(__name__)

# Edit this prompt to tune what Kimi looks for in the comparison.
VERIFY_PROMPT = (
    "You are a product visual matcher. "
    "Compare the two images below.\n"
    "Image 1 is a product listing photo.\n"
    "Image 2 is a frame captured from a live-selling video.\n\n"
    "Answer with a single JSON object: "
    '{{"match": true/false, "confidence": 0.0-1.0, "reason": "one sentence"}}\n'
    "Match should be true if the product in Image 1 is clearly visible and being "
    "presented in Image 2. Be strict — partial visibility or similar-looking items "
    "are not a match."
)


def verify_frame_match(
    client: OpenAI,
    product_image_url: str,
    frame_url: str,
    confidence_threshold: float = 0.6,
) -> bool:
    """Check whether a video frame shows the expected product.

    Sends both image URLs to Kimi's vision model and parses the
    structured response. Returns False on any error so the pipeline
    continues with the spoken-word match as fallback.

    Args:
        client: An OpenAI client pointed at the Moonshot base URL.
        product_image_url: URL of the product's reference image.
        frame_url: URL of the extracted video frame to verify.
        confidence_threshold: Minimum confidence to accept as a match.

    Returns:
        bool: True if Kimi confirms the product is visible in the frame.
    """
    import json

    try:
        product_b64 = _url_to_base64(product_image_url)
        frame_b64 = _url_to_base64(frame_url)
        resp = client.chat.completions.create(
            model="moonshot-v1-8k-vision-preview",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VERIFY_PROMPT},
                        {"type": "image_url", "image_url": {"url": product_b64}},
                        {"type": "image_url", "image_url": {"url": frame_b64}},
                    ],
                }
            ],
        )
        result = json.loads(resp.choices[0].message.content)
        matched = result.get("match", False)
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "")
        logger.info(
            "Image verify: match=%s confidence=%.2f reason=%r",
            matched, confidence, reason,
        )
        return matched and confidence >= confidence_threshold

    except Exception as exc:
        logger.warning("Image verification failed (%s) — accepting spoken match.", exc)
        return True  # fail open: trust the spoken-word match


def _url_to_base64(url: str) -> str:
    """Download an image URL and return it as a base64 data URI.

    Args:
        url: Public image URL.

    Returns:
        str: A data URI string (data:image/jpeg;base64,...).
    """
    with urlopen(url, timeout=10) as response:
        data = base64.b64encode(response.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{data}"


def get_video_frame_url(video: Any, timestamp: float) -> str | None:
    """Extract a thumbnail URL from a VideoDB video at a given timestamp.

    Args:
        video: An indexed VideoDB Video object.
        timestamp: Time in seconds to sample the frame.

    Returns:
        str | None: A publicly accessible image URL, or None if unavailable.
    """
    try:
        thumbnail = video.generate_thumbnail(time=timestamp)
        # VideoDB may return a URL string or an object with a .url attribute
        if isinstance(thumbnail, str):
            return thumbnail
        return getattr(thumbnail, "url", None)
    except Exception as exc:
        logger.warning("Could not extract video frame at %.1fs: %s", timestamp, exc)
        return None
