import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web import server


def test_web_runner_requires_a_source_url(monkeypatch):
    monkeypatch.setattr(server.config, "processing_enabled", lambda: True)
    client = server.app.test_client()
    response = client.post("/api/run", json={"limit": 3})

    assert response.status_code == 400
    assert response.get_json()["error"] == "A public HTTPS video URL is required."


def test_web_runner_rejects_an_out_of_bounds_limit(monkeypatch):
    monkeypatch.setattr(server.config, "validate_web_video_source", lambda value: value)
    monkeypatch.setattr(server.config, "processing_enabled", lambda: True)
    client = server.app.test_client()
    response = client.post("/api/run", json={"video_source": "https://media.example/demo.mp4", "limit": 7})

    assert response.status_code == 400
    assert "between 1 and 3" in response.get_json()["error"]


def test_web_runner_requires_explicit_operator_gate(monkeypatch):
    server._set_state("idle", "Ready.")
    monkeypatch.setattr(server.config, "processing_enabled", lambda: False)

    def should_not_validate(_: str) -> str:
        raise AssertionError("disabled public operation must not validate or resolve a source")

    monkeypatch.setattr(server.config, "validate_web_video_source", should_not_validate)

    response = server.app.test_client().post(
        "/api/run", json={"video_source": "https://media.example/demo.mp4", "limit": 1}
    )

    assert response.status_code == 403
    assert "disabled" in response.get_json()["error"]


def test_public_showcase_serves_three_fixture_backed_runs_and_full_pages(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    client = server.app.test_client()

    status = client.get("/api/status")
    runs = client.get("/api/prepared-runs")
    clips = client.get("/api/clips?run=trail-essentials-v1")

    assert status.get_json() == {
        "message": "Prepared illustrative demo - not a live VideoDB/provider run.",
        "mode": "showcase",
        "prepared_run_count": 3,
        "progress": 100,
        "status": "done",
    }
    assert len(runs.get_json()) == 3
    assert clips.get_json() == server.prepared_run("trail-essentials-v1")["clips"]
    assert client.get("/api/clips?run=unknown").status_code == 404
    assert b"UPLOAD VIDEO" in client.get("/").data
    assert b"Prepared examples" in client.get("/api/showcase").data
    assert b"Prepared examples" in client.get("/api/showcase/results").data
    for asset in ("home-tabletop.svg", "trail-essentials.svg", "focus-desk.svg"):
        assert client.get(f"/assets/{asset}").status_code == 200


def test_public_run_is_disabled_before_any_source_validation_without_services(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")

    def should_not_validate(_: str) -> str:
        raise AssertionError("public showcase must not inspect external video URLs")

    monkeypatch.setattr(server.config, "validate_web_video_source", should_not_validate)
    response = server.app.test_client().post("/api/run", json={"video_source": "https://media.example/demo.mp4"})

    assert response.status_code == 403
    assert "disabled" in response.get_json()["error"]


def test_web_runner_creates_a_durable_job(monkeypatch):
    observed = {}
    monkeypatch.setattr(server.config, "validate_web_video_source", lambda value: value)
    monkeypatch.setattr(server.config, "processing_enabled", lambda: True)
    def fake_create_run(**kwargs):
        observed.update(kwargs)
        return {"id": "c35bc73f-50bf-48eb-90bd-639afc51c0c7", "status": "queued"}
    monkeypatch.setattr(server, "create_run", fake_create_run)

    response = server.app.test_client().post(
        "/api/run", json={"video_source": "https://media.example/demo.mp4", "limit": 1}
    )

    assert response.status_code == 202
    assert observed["product_limit"] == 1
    assert observed["video_source"] == "https://media.example/demo.mp4"


def test_process_endpoint_returns_durable_state(monkeypatch):
    monkeypatch.setattr(server.config, "processing_enabled", lambda: True)
    monkeypatch.setattr(server, "process_next", lambda run_id: {"id": run_id, "status": "queued", "step": "product"})
    run_id = "c35bc73f-50bf-48eb-90bd-639afc51c0c7"
    response = server.app.test_client().post(f"/api/run/{run_id}/process")
    assert response.status_code == 200
    assert response.get_json()["step"] == "product"
