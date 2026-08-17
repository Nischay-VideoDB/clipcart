import socket

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


@pytest.mark.parametrize("source", ["http://media.example/video.mp4", "https://localhost/video.mp4", "https://127.0.0.1/video.mp4"])
def test_validate_web_video_source_rejects_non_public_sources(source):
    with pytest.raises(ValueError):
        config.validate_web_video_source(source)
