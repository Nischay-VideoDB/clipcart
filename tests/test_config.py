import json
import socket
from pathlib import Path

import pytest

from clipcart import config


def test_validate_web_video_source_accepts_public_https(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_: [(None, None, None, None, ("8.8.8.8", 0))])
    assert config.validate_web_video_source("https://media.example/video.mp4") == "https://media.example/video.mp4"


def test_video_cache_is_kept_outside_browser_output(monkeypatch, tmp_path):
    public_output = tmp_path / "output"
    private_state = tmp_path / "state"
    monkeypatch.setenv("CLIPCART_DATA_DIR", str(public_output))
    monkeypatch.setenv("CLIPCART_STATE_DIR", str(private_state))

    assert config.clips_output_path() == public_output / "clips.json"
    assert config.video_cache_path() == private_state / "video_cache.json"
    assert config.video_cache_path().parent != config.output_dir()


def test_vercel_never_enables_processing(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("CLIPCART_ALLOW_PROCESSING", "true")

    assert config.processing_enabled() is False
    assert config.public_showcase() is True


def test_prepared_illustrative_records_match_the_tracked_catalog_fixture():
    catalog = json.loads(Path(config.SAMPLE_CATALOG_PATH).read_text())
    clips = json.loads(config.PREPARED_ILLUSTRATIVE_CLIPS_PATH.read_text())

    assert [clip["name"] for clip in clips] == [product["name"] for product in catalog]
    assert [clip["price"] for clip in clips] == [product["price"] for product in catalog]
    assert [clip["buy_url"] for clip in clips] == [product["buy_url"] for product in catalog]
    assert all(clip["end"] > clip["start"] and not clip["stream_url"] for clip in clips)
    assert all("No provider generated" in clip["caption"] for clip in clips)


def test_vercel_routes_the_full_prepared_pages_through_the_function():
    route_config = json.loads((Path(__file__).resolve().parents[1] / "vercel.json").read_text())

    assert {route["source"]: route["destination"] for route in route_config["rewrites"]} == {
        "/": "/api/index.py?path=showcase",
        "/results.html": "/api/index.py?path=showcase/results",
        "/api/:path*": "/api/index.py",
    }


@pytest.mark.parametrize("source", ["http://media.example/video.mp4", "https://localhost/video.mp4", "https://127.0.0.1/video.mp4"])
def test_validate_web_video_source_rejects_non_public_sources(source):
    with pytest.raises(ValueError):
        config.validate_web_video_source(source)
