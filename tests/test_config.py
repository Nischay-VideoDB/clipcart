import json
import socket
from pathlib import Path

import pytest

from clipcart import config
from clipcart.prepared_demo import PREPARED_ILLUSTRATIVE_CLIPS


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
    clips = PREPARED_ILLUSTRATIVE_CLIPS
    public_clips = json.loads((config.PROJECT_ROOT / "public" / "prepared_illustrative_clips.json").read_text())

    assert [clip["name"] for clip in clips] == [product["name"] for product in catalog]
    assert [clip["price"] for clip in clips] == [product["price"] for product in catalog]
    assert [clip["buy_url"] for clip in clips] == [product["buy_url"] for product in catalog]
    assert all(clip["end"] > clip["start"] and not clip["stream_url"] for clip in clips)
    assert all("No provider generated" in clip["caption"] for clip in clips)
    assert public_clips == clips


def test_vercel_routes_the_full_prepared_pages_through_the_function():
    route_config = json.loads((Path(__file__).resolve().parents[1] / "vercel.json").read_text())

    assert {route["source"]: route["destination"] for route in route_config["rewrites"]} == {
        "/favicon.ico": "/favicon.svg",
        "/": "/api/index.py?path=showcase",
        "/results.html": "/api/index.py?path=showcase/results",
        "/api/:path*": "/api/index.py",
    }


def test_public_pages_include_mobile_layout_guards_and_the_branded_favicon():
    project_root = Path(__file__).resolve().parents[1]
    favicon = project_root / "public" / "favicon.svg"

    assert "ClipCart" in favicon.read_text()
    for page in (project_root / "web" / "index.html", project_root / "web" / "results.html"):
        source = page.read_text()

        assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml">' in source
        assert "overflow-x: clip" in source
        assert "@media (max-width: 600px)" in source
        assert "@media (max-width: 390px)" in source

    home_source = (project_root / "web" / "index.html").read_text()
    results_source = (project_root / "web" / "results.html").read_text()
    assert ".hero { flex-direction: column;" in home_source
    assert ".stats-bar { display: grid;" in home_source
    assert ".header-stats { width: 100%; justify-content: space-between;" in results_source
    assert ".widget-body { height: auto; flex-direction: column;" in results_source


@pytest.mark.parametrize("source", ["http://media.example/video.mp4", "https://localhost/video.mp4", "https://127.0.0.1/video.mp4"])
def test_validate_web_video_source_rejects_non_public_sources(source):
    with pytest.raises(ValueError):
        config.validate_web_video_source(source)
