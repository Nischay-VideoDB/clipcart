import socket

import pytest

from clipcart import config


def test_validate_web_video_source_accepts_public_https(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_: [(None, None, None, None, ("8.8.8.8", 0))])
    assert config.validate_web_video_source("https://media.example/video.mp4") == "https://media.example/video.mp4"


@pytest.mark.parametrize("source", ["http://media.example/video.mp4", "https://localhost/video.mp4", "https://127.0.0.1/video.mp4"])
def test_validate_web_video_source_rejects_non_public_sources(source):
    with pytest.raises(ValueError):
        config.validate_web_video_source(source)
