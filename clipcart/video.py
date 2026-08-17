"""VideoDB: connect, upload (URL or local file), index, and spoken-word search."""

import logging
from pathlib import Path
from typing import Any

import videodb
from videodb import IndexType

from clipcart.config import get_env

logger = logging.getLogger(__name__)


def connect() -> Any:
    """Return an authenticated VideoDB connection.

    Reads VIDEO_DB_API_KEY from the environment.

    Returns:
        A VideoDB connection object.
    """
    api_key = get_env("VIDEO_DB_API_KEY", required=True)
    return videodb.connect(api_key=api_key)


def get_or_upload(conn: Any, source: str, cache_path: str = "output/video_cache.json") -> Any:
    """Return an already-uploaded video if cached, otherwise upload and index.

    Saves the video ID to a JSON file so subsequent runs skip the upload.
    Delete output/video_cache.json to force a fresh upload.

    Args:
        conn: An authenticated VideoDB connection.
        source: A URL or local file path (used as the cache key).
        cache_path: Path to the JSON cache file.

    Returns:
        The indexed VideoDB Video object.
    """
    import json
    from pathlib import Path

    cache_file = Path(cache_path)
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
            if cache.get("source") == source and cache.get("video_id"):
                video_id = cache["video_id"]
                logger.info("Using cached video id=%s (delete %s to re-upload).", video_id, cache_path)
                coll = conn.get_collection()
                return coll.get_video(video_id)
        except Exception as exc:
            logger.warning("Could not read video cache (%s) — re-uploading.", exc)

    video = upload_and_index(conn, source)

    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps({"source": source, "video_id": video.id}))
    logger.info("Cached video id=%s to %s.", video.id, cache_path)
    return video


def upload_and_index(conn: Any, source: str) -> Any:
    """Upload a video and index its spoken words.

    Accepts either a remote URL or a local file path. Indexing can take
    several minutes on first run — pre-index the sample video before the demo.

    Args:
        conn: An authenticated VideoDB connection.
        source: A URL (http/https) or a local file path.

    Returns:
        The indexed VideoDB Video object.
    """
    source = str(source)
    if source.startswith("http://") or source.startswith("https://"):
        logger.info("Uploading video from URL")
        video = conn.upload(url=source)
    elif Path(source).exists():
        logger.info("Uploading video from local file: %s", source)
        video = conn.upload(file_path=source)
    else:
        raise FileNotFoundError(
            f"Video source is not a valid URL or existing file path: {source!r}"
        )

    logger.info("Indexing spoken words for video id=%s (this may take a few minutes)...", video.id)
    video.index_spoken_words()
    logger.info("Indexing complete.")
    return video


def search_spoken(video: Any, query: str) -> list[Any]:
    """Return ranked shots for a spoken-word query.

    Args:
        video: An indexed VideoDB Video object.
        query: The search string (e.g. a product name).

    Returns:
        list: Shot objects with .start, .end, and .text attributes.
    """
    logger.debug("Searching spoken words for query: %r", query)
    results = video.search(query, index_type=IndexType.spoken_word)
    shots = results.get_shots()
    logger.debug("Found %d shot(s) for query %r", len(shots), query)
    return shots
