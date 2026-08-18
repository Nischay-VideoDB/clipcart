"""ClipCart dev server: serves the UI and exposes the pipeline API.

Run:
    uv run python web/server.py

Endpoints:
    GET  /                  → web/index.html
    GET  /api/clips         → output/clips.json (or [])
    GET  /api/status        → {status, message, progress}
    POST /api/run           → start pipeline; body JSON {video_source, limit}
"""

import json
import logging
import os
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

# resolve project root (one level up from web/)
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from clipcart import config  # noqa: E402
from clipcart.prepared_demo import (  # noqa: E402
    PREPARED_ILLUSTRATIVE_CLIPS,
    prepared_run,
    prepared_runs,
)
from clipcart.pipeline import run as run_pipeline  # noqa: E402
from clipcart.jobs import create_run, get_run, init_jobs, process_next  # noqa: E402

app = Flask(__name__, static_folder=str(ROOT / "web"))
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# Shared state is guarded for one local operator. It is not a durable job queue.
_state: dict = {"status": "idle", "message": "Ready.", "progress": 0}
_lock = threading.Lock()


def _output_dir() -> Path:
    path = config.output_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _set_state(status: str, message: str, progress: int = 0) -> None:
    with _lock:
        _state["status"] = status
        _state["message"] = message
        _state["progress"] = progress


def _prepared_illustrative_clips() -> str:
    """Return fixture-backed illustrative records for the public showcase only."""
    return json.dumps(PREPARED_ILLUSTRATIVE_CLIPS)


def _prepared_run_response(run_id: str | None):
    try:
        return prepared_run(run_id)
    except KeyError:
        return None


@app.route("/")
def index():
    """Serve the live workflow; prepared examples are an additive route."""
    return send_from_directory(str(ROOT / "web"), "index.html")


@app.route("/api/showcase")
def showcase_index():
    """Make the prepared examples the public Vercel entrypoint."""
    return send_from_directory(str(ROOT / "web"), "results.html")


@app.route("/assets/<path:filename>")
def prepared_assets(filename: str):
    """Serve prepared product art locally; Vercel serves public/assets directly."""
    return send_from_directory(str(ROOT / "public" / "assets"), filename)


@app.route("/api/showcase/results")
def showcase_results():
    """Serve the prepared results page through the Vercel function."""
    return send_from_directory(str(ROOT / "web"), "results.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    """Serve static assets (CSS, JS, images)."""
    return send_from_directory(str(ROOT / "web"), filename)


@app.route("/output/<path:filename>")
def output_files(filename: str):
    """Serve generated output files (clips.json, etc.)."""
    return send_from_directory(str(_output_dir()), filename)


@app.route("/api/clips")
def get_clips():
    """Return the current clips.json or an empty list."""
    selected_id = request.args.get("run")
    if selected_id:
        selected_run = _prepared_run_response(selected_id)
        if selected_run is not None:
            return jsonify(selected_run["clips"])
        live_run = get_run(selected_id) if config.processing_enabled() else None
        if live_run is None:
            return jsonify({"error": "Unknown run."}), 404
        return jsonify(live_run["clips"])
    if os.getenv("VERCEL"):
        selected_run = _prepared_run_response(None)
        if selected_run is None:
            return jsonify({"error": "Unknown prepared example."}), 404
        return jsonify(selected_run["clips"])
    clips_path = config.clips_output_path()
    if clips_path.exists():
        return clips_path.read_text(encoding="utf-8"), 200, {"Content-Type": "application/json"}
    return jsonify([])


@app.route("/api/prepared-runs")
def get_prepared_runs():
    """Expose only static, transparent examples for the public showcase selector."""
    return jsonify(prepared_runs())


@app.route("/api/status")
def get_status():
    """Return current pipeline status."""
    run_id = request.args.get("run")
    if run_id and config.processing_enabled():
        live_run = get_run(run_id)
        if live_run is None:
            return jsonify({"error": "Unknown run."}), 404
        return jsonify({**live_run, "mode": "live"})
    if os.getenv("VERCEL"):
        return jsonify({
            "status": "done",
            "message": "Prepared illustrative demo - not a live VideoDB/provider run.",
            "progress": 100,
            "mode": "showcase",
            "prepared_run_count": len(prepared_runs()),
        })
    with _lock:
        return jsonify(dict(_state))


@app.route("/api/capabilities")
def capabilities():
    enabled = config.processing_enabled()
    return jsonify({
        "mode": "operator" if enabled else "showcase",
        "processing_enabled": enabled,
        "message": (
            "Durable live processing is enabled; prepared examples remain available."
            if enabled
            else "Live processing is unavailable because required server services are not configured."
        ),
    })


@app.route("/api/run", methods=["POST"])
def start_run():
    """Create an idempotent durable run. Provider work is executed by step calls.

    Expected JSON body:
        video_source (str): URL or local file path.
        limit (int): Max products to process (default 3).
        no_image_verify (bool): Skip Kimi image check (default false).
    """
    if not config.processing_enabled():
        return jsonify({
            "error": "Live processing is disabled in this prepared-data showcase. Run the local operator workflow with CLIPCART_ALLOW_PROCESSING=true.",
        }), 403

    body = request.get_json(silent=True) or {}
    source_value = body.get("video_source")
    if not isinstance(source_value, str) or not source_value.strip():
        return jsonify({"error": "A public HTTPS video URL is required."}), 400
    try:
        video_source = config.validate_web_video_source(source_value)
        limit = int(body.get("limit", 3))
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    if not 1 <= limit <= config.DEFAULT_LIMIT:
        return jsonify({"error": f"Products must be between 1 and {config.DEFAULT_LIMIT}."}), 400
    no_image_verify = body.get("no_image_verify", False) is True

    idem = request.headers.get("Idempotency-Key", "").strip()
    if not idem:
        idem = str(uuid.uuid4())
    if len(idem) > 120:
        return jsonify({"error": "Idempotency-Key must be at most 120 characters."}), 400
    requester = request.headers.get("X-Forwarded-For", request.remote_addr or "anonymous").split(",")[0].strip()
    try:
        created = create_run(
            video_source=video_source, product_limit=limit,
            skip_image_verify=no_image_verify, idempotency_key=idem, requester=requester,
        )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 429
    return jsonify(created), 202


@app.route("/api/run/<run_id>/process", methods=["POST"])
def process_run_step(run_id: str):
    """Execute or retry one leased, durable provider step."""
    if not config.processing_enabled():
        return jsonify({"error": "Live processing is not configured."}), 503
    try:
        result = process_next(run_id)
    except (ValueError, KeyError):
        return jsonify({"error": "Unknown run."}), 404
    return jsonify(result)


if __name__ == "__main__":
    print(f"ClipCart server running at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
