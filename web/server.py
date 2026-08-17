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
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

# resolve project root (one level up from web/)
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from clipcart import config  # noqa: E402
from clipcart.pipeline import run as run_pipeline  # noqa: E402

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


@app.route("/")
def index():
    """Serve the main UI."""
    return send_from_directory(str(ROOT / "web"), "index.html")


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
    clips_path = config.clips_output_path()
    if clips_path.exists():
        return clips_path.read_text(encoding="utf-8"), 200, {"Content-Type": "application/json"}
    return jsonify([])


@app.route("/api/status")
def get_status():
    """Return current pipeline status."""
    with _lock:
        return jsonify(dict(_state))


@app.route("/api/capabilities")
def capabilities():
    enabled = config.processing_enabled()
    return jsonify({
        "mode": "operator" if enabled else "showcase",
        "processing_enabled": enabled,
        "message": (
            "Local operator processing is enabled."
            if enabled
            else "This is a prepared-data showcase. Live processing is disabled."
        ),
    })


@app.route("/api/run", methods=["POST"])
def start_run():
    """Start the pipeline in a background thread.

    Expected JSON body:
        video_source (str): URL or local file path.
        limit (int): Max products to process (default 3).
        no_image_verify (bool): Skip Kimi image check (default false).
    """
    with _lock:
        if _state["status"] == "running":
            return jsonify({"error": "Pipeline already running."}), 409

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

    if not config.processing_enabled():
        return jsonify({
            "error": "Live processing is disabled in this prepared-data showcase. Run the local operator workflow with CLIPCART_ALLOW_PROCESSING=true.",
        }), 403

    def _run():
        _set_state("running", "Preparing the video for analysis.", progress=5)
        try:
            clips = run_pipeline(
                video_source=video_source,
                limit=limit,
                out_path=str(config.clips_output_path()),
                use_image_verify=not no_image_verify,
            )
            _set_state("done", f"Done — {len(clips)} clip(s) generated.", progress=100)
        except Exception as exc:
            logger.exception("Pipeline failed")
            _set_state("error", "The pipeline could not complete. Review server logs and try again.", progress=0)

    with _lock:
        if _state["status"] == "running":
            return jsonify({"error": "Pipeline already running."}), 409
        _state.update({"status": "running", "message": "Preparing the video for analysis.", "progress": 5})
        threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "running", "message": "Pipeline started."})


if __name__ == "__main__":
    print(f"ClipCart server running at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
