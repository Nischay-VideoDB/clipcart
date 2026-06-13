"""Configuration: load env vars and expose pipeline constants."""

import os
from dotenv import load_dotenv

load_dotenv()

MIN_CLIP_LEN: float = 12.0
MAX_CLIP_LEN: float = 40.0
LEAD_SECONDS: float = 8.0
DEFAULT_LIMIT: int = 6

SAMPLE_VIDEO_SOURCE: str = "data/the_style_soiree_live.mp4"  # local file path or URL
SAMPLE_CATALOG_PATH: str = "data/catalog.sample.json"


def get_env(name: str, required: bool = False) -> str | None:
    """Return an environment variable value.

    Args:
        name: Environment variable name.
        required: If True, raises ValueError when the variable is missing.

    Returns:
        The variable's value, or None if not set and not required.

    Raises:
        ValueError: If required is True and the variable is not set.
    """
    value = os.getenv(name)
    if required and not value:
        raise ValueError(f"Required env var {name!r} is not set. Check your .env file.")
    return value
