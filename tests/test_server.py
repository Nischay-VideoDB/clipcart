import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web import server


def test_web_runner_requires_a_source_url():
    client = server.app.test_client()
    response = client.post("/api/run", json={"limit": 3})

    assert response.status_code == 400
    assert response.get_json()["error"] == "A public HTTPS video URL is required."


def test_web_runner_rejects_an_out_of_bounds_limit(monkeypatch):
    monkeypatch.setattr(server.config, "validate_web_video_source", lambda value: value)
    client = server.app.test_client()
    response = client.post("/api/run", json={"video_source": "https://media.example/demo.mp4", "limit": 7})

    assert response.status_code == 400
    assert "between 1 and 6" in response.get_json()["error"]


def test_web_runner_requires_explicit_operator_gate(monkeypatch):
    server._set_state("idle", "Ready.")
    monkeypatch.setattr(server.config, "validate_web_video_source", lambda value: value)
    monkeypatch.setattr(server.config, "processing_enabled", lambda: False)

    response = server.app.test_client().post(
        "/api/run", json={"video_source": "https://media.example/demo.mp4", "limit": 1}
    )

    assert response.status_code == 403
    assert "disabled" in response.get_json()["error"]


def test_web_runner_marks_running_before_starting_worker(monkeypatch):
    observed = {}

    class FakeThread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            observed.update(server._state)

    server._set_state("idle", "Ready.")
    monkeypatch.setattr(server.config, "validate_web_video_source", lambda value: value)
    monkeypatch.setattr(server.config, "processing_enabled", lambda: True)
    monkeypatch.setattr(server.threading, "Thread", FakeThread)

    response = server.app.test_client().post(
        "/api/run", json={"video_source": "https://media.example/demo.mp4", "limit": 1}
    )

    assert response.status_code == 200
    assert observed["status"] == "running"
    server._set_state("idle", "Ready.")
