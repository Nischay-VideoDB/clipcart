"""Configuration: load env vars and expose pipeline constants."""

import os
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

MIN_CLIP_LEN: float = 12.0
MAX_CLIP_LEN: float = 40.0
LEAD_SECONDS: float = 8.0
DEFAULT_LIMIT: int = 3

SAMPLE_CATALOG_PATH: str = str(PROJECT_ROOT / "fixtures" / "catalog.sample.json")


def output_dir() -> Path:
    """Return the public/generated clip-output directory."""
    value = os.getenv("CLIPCART_DATA_DIR")
    return Path(value).expanduser().resolve() if value else PROJECT_ROOT / "output"


def clips_output_path() -> Path:
    return output_dir() / "clips.json"


def video_cache_path() -> Path:
    """Keep provider upload IDs out of the browser-served output directory."""
    value = os.getenv("CLIPCART_STATE_DIR")
    state_dir = Path(value).expanduser().resolve() if value else PROJECT_ROOT / "state"
    return state_dir / "video_cache.json"


def processing_enabled() -> bool:
    """Enable the durable public runner only when all required services exist."""
    explicitly_enabled = os.getenv("CLIPCART_ALLOW_PROCESSING", "").lower() in {"1", "true", "yes"}
    return explicitly_enabled and bool(
        os.getenv("DATABASE_URL") and os.getenv("VIDEO_DB_API_KEY")
    )


def public_showcase() -> bool:
    """Prepared examples remain available, but are no longer the only public mode."""
    return False


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


def validate_web_video_source(source: str) -> str:
    """Allow the web runner to fetch only publicly resolvable HTTPS media URLs.

    Local paths remain available to the CLI. The browser-facing route rejects
    loopback and private-network destinations before handing a URL to VideoDB.
    """
    parsed = urlparse(source.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Provide a public HTTPS video URL.")

    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("Local and private network video sources are not allowed.")

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise ValueError("The video source hostname could not be resolved.") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise ValueError("Local and private network video sources are not allowed.")
    return source.strip()
