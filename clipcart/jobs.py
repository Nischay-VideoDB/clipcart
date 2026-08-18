"""Durable, database-backed orchestration for public ClipCart runs.

Each invocation leases and executes one provider-sized step. The browser may
disconnect at any point: the next invocation resumes from the committed step.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from clipcart import config
from clipcart.catalog import load_catalog
from clipcart.clipper import build_clip
from clipcart.copywriter import make_client, write_copy
from clipcart.matcher import find_product_window
from clipcart.pipeline import _get_transcript
from clipcart.video import connect


def _database_url() -> str:
    value = os.environ["DATABASE_URL"]
    return value.replace("sslmode=no-verify", "sslmode=require")


def init_jobs() -> None:
    with psycopg.connect(_database_url()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clipcart_runs (
              id UUID PRIMARY KEY,
              idempotency_key TEXT UNIQUE NOT NULL,
              requester_hash TEXT NOT NULL,
              video_source TEXT NOT NULL,
              product_limit INTEGER NOT NULL CHECK (product_limit BETWEEN 1 AND 3),
              skip_image_verify BOOLEAN NOT NULL DEFAULT TRUE,
              status TEXT NOT NULL DEFAULT 'queued',
              step TEXT NOT NULL DEFAULT 'upload',
              current_product INTEGER NOT NULL DEFAULT 0,
              video_id TEXT,
              clips JSONB NOT NULL DEFAULT '[]'::jsonb,
              provider_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              locked_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              completed_at TIMESTAMPTZ
            )
            """
        )


def requester_hash(value: str) -> str:
    salt = os.getenv("CLIPCART_REQUEST_SALT", "clipcart-public-v1")
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


def create_run(
    *, video_source: str, product_limit: int, skip_image_verify: bool,
    idempotency_key: str, requester: str,
) -> dict[str, Any]:
    init_jobs()
    identity = requester_hash(requester)
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        # An idempotent replay must remain retrievable after the requester has
        # reached the creation quota. The key is an unguessable client token and
        # never starts another provider run.
        existing = conn.execute(
            "SELECT * FROM clipcart_runs WHERE idempotency_key=%s",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return _public(existing)
        recent = conn.execute(
            "SELECT count(*) AS n FROM clipcart_runs WHERE requester_hash=%s AND created_at > now() - interval '1 hour'",
            (identity,),
        ).fetchone()["n"]
        if recent >= 3:
            raise PermissionError("Public demo limit reached: three new runs per hour.")
        run_id = uuid.uuid4()
        row = conn.execute(
            """
            INSERT INTO clipcart_runs
              (id, idempotency_key, requester_hash, video_source, product_limit, skip_image_verify)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (idempotency_key) DO UPDATE SET updated_at=now()
            RETURNING *
            """,
            (run_id, idempotency_key, identity, video_source, product_limit, skip_image_verify),
        ).fetchone()
        return _public(row)


def get_run(run_id: str) -> dict[str, Any] | None:
    try:
        parsed = uuid.UUID(run_id)
    except ValueError:
        return None
    init_jobs()
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        row = conn.execute("SELECT * FROM clipcart_runs WHERE id=%s", (parsed,)).fetchone()
        return _public(row) if row else None


def process_next(run_id: str) -> dict[str, Any]:
    """Lease one run and execute exactly one durable step."""
    parsed = uuid.UUID(run_id)
    init_jobs()
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        row = conn.execute(
            """
            UPDATE clipcart_runs SET status='running', locked_at=now(), attempts=attempts+1,
              error=NULL, updated_at=now()
            WHERE id=%s AND status IN ('queued','running','retry')
              AND (locked_at IS NULL OR locked_at < now() - interval '10 minutes')
            RETURNING *
            """,
            (parsed,),
        ).fetchone()
    if not row:
        current = get_run(run_id)
        if not current:
            raise KeyError(run_id)
        return current

    try:
        if row["step"] == "upload":
            _upload_step(row)
        elif row["step"] == "product":
            _product_step(row)
        return get_run(run_id) or {}
    except Exception as exc:
        # Retry provider failures twice; preserve a concise, non-secret reason.
        terminal = row["attempts"] >= 3
        with psycopg.connect(_database_url()) as conn:
            conn.execute(
                """UPDATE clipcart_runs SET status=%s, error=%s, locked_at=NULL,
                   updated_at=now() WHERE id=%s""",
                ("failed" if terminal else "retry", _safe_error(exc), parsed),
            )
        return get_run(run_id) or {}


def _upload_step(row: dict[str, Any]) -> None:
    conn = connect()
    coll = conn.get_collection()
    video = coll.upload(url=row["video_source"])
    video.index_spoken_words()
    evidence = {
        "videodb_video_id": video.id,
        "indexed_spoken_words": True,
        "source": "videodb-live",
    }
    with psycopg.connect(_database_url()) as db:
        db.execute(
            """UPDATE clipcart_runs SET video_id=%s, provider_evidence=%s,
               step='product', status='queued', attempts=0, locked_at=NULL,
               updated_at=now() WHERE id=%s""",
            (video.id, json.dumps(evidence), row["id"]),
        )


def _product_step(row: dict[str, Any]) -> None:
    products = load_catalog(path=config.SAMPLE_CATALOG_PATH, limit=row["product_limit"])
    idx = row["current_product"]
    if idx >= len(products):
        _complete(row["id"])
        return

    product = products[idx]
    conn = connect()
    video = conn.get_collection().get_video(row["video_id"])
    kimi = make_client()
    window = find_product_window(
        video=video, product=product, min_len=config.MIN_CLIP_LEN,
        max_len=config.MAX_CLIP_LEN, lead=config.LEAD_SECONDS,
        kimi_client=None if row["skip_image_verify"] else kimi,
    )
    clips = list(row["clips"] or [])
    if window:
        stream_url = build_clip(conn, video, window, product)
        copy = write_copy(kimi, product, _get_transcript(video, window))
        clips.append({
            "name": product["name"], "price": product["price"],
            "buy_url": product["buy_url"], "image_url": product.get("image_url", ""),
            "hook": copy.get("hook", ""), "caption": copy.get("caption", ""),
            "hashtags": copy.get("hashtags", []),
            "schedule": copy.get("post_offset_hours", 24),
            "stream_url": stream_url, "start": window[0], "end": window[1],
            "provider": "VideoDB live pipeline",
        })
    next_idx = idx + 1
    done = next_idx >= len(products)
    with psycopg.connect(_database_url()) as db:
        db.execute(
            """UPDATE clipcart_runs SET clips=%s, current_product=%s, status=%s,
               step=%s, attempts=0, locked_at=NULL, updated_at=now(),
               completed_at=CASE WHEN %s THEN now() ELSE completed_at END
               WHERE id=%s""",
            (json.dumps(clips), next_idx, "done" if done else "queued",
             "done" if done else "product", done, row["id"]),
        )


def _complete(run_id: uuid.UUID) -> None:
    with psycopg.connect(_database_url()) as conn:
        conn.execute(
            "UPDATE clipcart_runs SET status='done', step='done', locked_at=NULL, completed_at=now(), updated_at=now() WHERE id=%s",
            (run_id,),
        )


def _safe_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    return (text[:240] or exc.__class__.__name__)


def _public(row: dict[str, Any]) -> dict[str, Any]:
    progress = 5
    if row["video_id"]:
        progress = 35 + round(65 * row["current_product"] / max(row["product_limit"], 1))
    if row["status"] == "done":
        progress = 100
    message = {
        "queued": "Ready for the next durable processing step.",
        "running": "A provider step is running.",
        "retry": "A provider step failed; retry is available.",
        "done": f"Done — {len(row['clips'] or [])} live clip(s) generated.",
        "failed": row.get("error") or "The live run failed.",
    }.get(row["status"], row["status"])
    return {
        "id": str(row["id"]), "status": row["status"], "step": row["step"],
        "message": message, "progress": progress, "clips": row["clips"] or [],
        "provider_evidence": row["provider_evidence"] or {}, "error": row.get("error"),
        "created_at": row["created_at"].isoformat(),
        "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
    }
