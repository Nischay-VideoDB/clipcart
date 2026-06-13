# ClipCart — POC Implementation Spec (for Claude Code)

> **Read this first.** This is a hackathon POC. Build the **simplest thing that works end-to-end**, then stop. Prefer a working slice over completeness. Every external call must have a cached fallback so the live demo never hard-blocks. Follow the "What NOT to build" list — do not gold-plate.

---

## 1. Goal

Turn one live-selling video + a scraped product catalog into a small gallery of **shoppable vertical clips** — each trimmed to one product, with a price + buy-link overlay, auto-captions, and an AI-written hook.

**POC data story (say this in the demo):** Bright Data scrapes the Shopee catalog; we match each product to its moment in the video and tag the clip. In production, the seller connects their real Shopee account (Open Platform API) and we use the true order timeline instead. *Same pipeline, better data.* Keep that seam clean in code (see §9), but **do not build the production path** — stub it.

---

## 2. Pipeline (this is the whole app)

```
catalog (Bright Data scrape, or cached JSON)
      │   products: {name, price, buy_url, image_url}
      ▼
VideoDB: upload video once → index_spoken_words()
      │
for each product (limit ~6):
   match  → find the product's on-screen window via VideoDB spoken-word search
   clip   → VideoDB Timeline: trim + price/buy-link overlay + auto captions → stream_url
   copy   → Kimi K2.6: hook + caption + hashtags + post offset (one JSON call)
      ▼
write output/clips.json  →  static web gallery plays the clips
```

That's it. No live order data, no posting, no accounts.

---

## 3. Tech stack (minimal)

- **Python 3.11**, standard tooling. Core deps only: `videodb`, `openai` (used as the Kimi client), `requests`, `python-dotenv`. Add `beautifulsoup4` only if HTML parsing is needed.
- **Frontend:** a single static `web/index.html` (vanilla JS + `hls.js` from CDN). No framework, no build step.
- **No backend required** for the core POC — the pipeline is a CLI that writes `clips.json`; the gallery reads it. (An optional tiny FastAPI `/run` is a stretch, see §10.)

---

## 4. File structure

```
clipcart/
  __init__.py
  config.py        # load env vars + constants
  catalog.py       # CatalogSource: BrightData (POC) | cached fallback | Shopee stub
  video.py         # VideoDB connect, upload, index, spoken-word search
  matcher.py       # product -> (start, end) window
  clipper.py       # Timeline trim + overlay + captions -> stream_url
  copywriter.py    # Kimi: hook/caption/hashtags/schedule
  pipeline.py      # orchestrate; write output/clips.json
  run.py           # CLI entry point
data/
  catalog.sample.json   # cached catalog (fallback + default)
web/
  index.html            # static gallery (hls.js)
output/
  clips.json            # produced by the pipeline
.env.example
requirements.txt
README.md
```

---

## 5. Setup / env

`.env.example`:
```
VIDEO_DB_API_KEY=
MOONSHOT_API_KEY=          # Kimi K2.6 (https://api.moonshot.ai/v1)
BRIGHTDATA_API_TOKEN=      # optional; falls back to data/catalog.sample.json
# DAYTONA_API_KEY=         # optional (stretch, §10)
```

Run:
```
pip install -r requirements.txt
python -m clipcart.run --video <VIDEO_URL_OR_PATH> --catalog data/catalog.sample.json --limit 6
python -m http.server 8000 --directory web   # open http://localhost:8000
```

Defaults: if `--video`/`--catalog` are omitted, use a hardcoded sample video URL and `data/catalog.sample.json` so it runs with zero args.

---

## 6. Module specs

> All snippets are **illustrative** — confirm exact kwargs against the VideoDB / Moonshot docs. Code style: **PEP 8 + Google-style docstrings**, small pure functions, no clever abstractions.

### `config.py`
Load env vars with `python-dotenv`; expose constants: `MIN_CLIP_LEN=12.0`, `MAX_CLIP_LEN=40.0`, `LEAD_SECONDS=8.0` (how far before the product mention to start), `DEFAULT_LIMIT=6`. One `get_env(name, required=False)` helper.

### `catalog.py` — the Bright Data layer (with the production seam)
```python
def load_catalog(path, token=None, url=None, limit=6):
    """Return a list of product dicts for the POC.

    Tries a live Bright Data scrape when ``token`` and ``url`` are given,
    otherwise loads the cached JSON at ``path``. Always returns cached data
    if scraping fails, so the demo never blocks.

    Args:
        path: Path to the cached catalog JSON (fallback + default).
        token: Bright Data API token, or None to skip scraping.
        url: Shopee shop/live page to scrape, or None to skip scraping.
        limit: Max number of products to return.

    Returns:
        list[dict]: Products with keys ``name``, ``price``, ``buy_url``,
        ``image_url``.
    """
```
- Live scrape (optional): `POST https://api.brightdata.com/request` with `{"zone": "web_unlocker", "url": url, "format": "raw"}` and `Authorization: Bearer <token>`, then parse products. Wrap in try/except → fall back to cached JSON. **Do not block on scraping working.**
- Add a documented stub `def from_shopee_api(...)` that raises `NotImplementedError("production: seller connects Shopee account")`. This is the production seam — leave it unimplemented.

### `video.py` — VideoDB
```python
import videodb
from videodb import IndexType

def connect():
    """Return an authenticated VideoDB connection (reads VIDEO_DB_API_KEY)."""
    return videodb.connect()

def upload_and_index(conn, source):
    """Upload a video and index its spoken words.

    Args:
        conn: A VideoDB connection.
        source: A URL or local file path.

    Returns:
        The indexed VideoDB Video object.
    """
    video = conn.upload(url=source) if str(source).startswith("http") else conn.upload(file_path=source)
    video.index_spoken_words()
    return video

def search_spoken(video, query):
    """Return ranked shots (start/end/text) for a spoken-word query."""
    return video.search(query, index_type=IndexType.spoken_word).get_shots()
```
Index **once** per run. Indexing can take minutes — do it before the demo on the sample video.

### `matcher.py` — product → window (the core "tagging" step, kept simple)
```python
def find_product_window(video, product, min_len, max_len, lead):
    """Locate a product's on-screen window via spoken-word search.

    Picks the top shot for the product name, starts a little before it,
    and clamps the window to [min_len, max_len] seconds.

    Args:
        video: An indexed VideoDB Video.
        product: A dict with a ``name`` key.
        min_len: Minimum clip length (seconds).
        max_len: Maximum clip length (seconds).
        lead: Seconds to start before the matched mention.

    Returns:
        tuple[float, float] | None: (start, end) or None if no match.
    """
```
Logic (simple, no ML): search `product["name"]` → if no shots, return `None` (skip product); else take the best shot, `start = max(0, shot.start - lead)`, `end = max(shot.end, start + min_len)`, then cap `end - start` at `max_len`. Return `(start, end)`. **Do not** add scene-index or embeddings here — spoken search is enough for the POC. (Optional Nosana CLIP refinement is a stretch, §10.)

### `clipper.py` — VideoDB Timeline
```python
from videodb.timeline import Timeline
from videodb.asset import VideoAsset, TextAsset, CaptionAsset

def build_clip(conn, video, window, product):
    """Render a shoppable clip: trim + price/buy-link overlay + auto captions.

    Args:
        conn: A VideoDB connection.
        video: The indexed source Video.
        window: (start, end) seconds.
        product: A dict with ``price`` and ``buy_url``.

    Returns:
        str: An HLS stream URL for the clip.
    """
    start, end = window
    tl = Timeline(conn)
    tl.add_inline(VideoAsset(asset_id=video.id, start=start, end=end))
    tl.add_overlay(0, TextAsset(text=f"{product['price']}  |  {product['buy_url']}",
                                duration=end - start))
    tl.add_overlay(0, CaptionAsset(src="auto"))   # needs index_spoken_words()
    return tl.generate_stream()
```
**Vertical 9:16 is OPTIONAL.** `video.reframe()` is slow and can time out — skip it for the core POC and let the gallery present clips in a 9:16 frame via CSS. Only attempt reframe (on the short clip, in a try/except) if there's spare time.

### `copywriter.py` — Kimi K2.6
```python
import json
from openai import OpenAI

SYSTEM = ('Write a short-form shopping hook. Return STRICT JSON only: '
          '{"hook": str, "caption": str, "hashtags": [str], "post_offset_hours": int}.')

def write_copy(client, product, transcript):
    """Generate hook/caption/hashtags/post offset for one clip via Kimi.

    Args:
        client: An OpenAI client pointed at the Moonshot base URL.
        product: A dict with ``name`` and ``price``.
        transcript: The spoken text within the clip window.

    Returns:
        dict: Parsed JSON copy. Falls back to a basic dict on parse error.
    """
    resp = client.chat.completions.create(
        model="kimi-k2.6",
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"Product: {product}\nTranscript: {transcript}"}],
    )
    return json.loads(resp.choices[0].message.content)
```
Client: `OpenAI(api_key=MOONSHOT_API_KEY, base_url="https://api.moonshot.ai/v1")`. On any error, return a sensible fallback (`hook=product["name"]`, empty hashtags, `post_offset_hours=24`) so one bad call never breaks the run.

### `pipeline.py`
```python
def run(video_source, catalog_path, limit, out_path="output/clips.json"):
    """Run the full POC pipeline and write the gallery JSON.

    Steps: load catalog -> upload+index video -> for each product, match -> clip
    -> copy -> assemble a record. Products with no match are skipped.

    Returns:
        list[dict]: The clip records written to ``out_path``.
    """
```
- Run products **sequentially** for v1 (simplest). If there's time, parallelize the per-product loop with a `ThreadPoolExecutor` — this is the literal "Kimi swarm: one sub-agent per product" line for the pitch. Keep it to ~10 lines; don't build a task framework.
- Each record: `{name, price, buy_url, image_url, hook, caption, hashtags, schedule, stream_url, start, end}`.
- Write `clips.json` (pretty-printed). Print a one-line summary per product.

### `run.py`
`argparse` CLI: `--video`, `--catalog`, `--limit`, `--out`. Defaults wired to the sample so `python -m clipcart.run` works with no args.

---

## 7. The demo gallery — `web/index.html` (single file)

- Vanilla JS + `hls.js` from CDN. `fetch('../output/clips.json')` and render a responsive grid of cards.
- Each card: a **9:16 video frame** playing `stream_url` (hls.js), the **hook** as a heading, a **green price-tag chip**, the **caption**, the **scheduled time**, and a **buy-link** button.
- Dark theme to match the brand: background `#0B0A16`, cards `#17142B`, violet `#5B3FD6`, signature green `#21E116` (price tag + accents), text `#D8D5EC`. Keep the CSS short (~60 lines). No framework. This is enough to look good on a projector without over-building. (A polished React version can come from the separate Claude Design brief later — not now.)

---

## 8. Sample data (commit these so it runs offline)

- `data/catalog.sample.json`: ~6 products `{name, price, buy_url, image_url}` matching the demo video.
- The demo **video**: use your own recorded one-product-at-a-time live (full rights), referenced by URL or local path. The pipeline must run end-to-end on this sample with **no live API calls required** except VideoDB.

---

## 9. Production seams (keep clean, don't implement)

Two clearly-labeled stubs so the "real account later" story is visible in the code:
1. `catalog.from_shopee_api(shop_id, token)` → `NotImplementedError` with a comment: *production pulls catalog + real order timeline via Shopee Open Platform (OAuth).*
2. A comment in `matcher.py`: *POC infers the window from spoken search; production seeds it from the real `sale_timestamp` in the order data.*

That's the whole production story — one comment and one stub. No more.

---

## 10. Stretch only (do NOT start until §1–8 work end-to-end)

- **Nosana CLIP refine:** deploy a CLIP template endpoint; in `matcher.py`, rank a few candidate frames against `product["image_url"]` to tighten the window. Behind a `--use-nosana` flag, default off.
- **Daytona run wrapper:** `daytona_run.py` that executes `pipeline.run(...)` inside a sandbox (`Daytona().create()` → `sandbox.process.code_run(...)`). Thin; for the sponsor-usage story.
- **9:16 reframe** on short clips (try/except).
- **Tiny FastAPI `/run`** so the gallery has a live "Generate" button.
- **Live Bright Data scrape** wired in front of the cached fallback.

---

## 11. What NOT to build (avoid over-engineering)

- ❌ No database — JSON files only.
- ❌ No auth, no user accounts, no real Shopee OAuth (stub it).
- ❌ No auto-posting to TikTok/IG — output clips + a schedule field only.
- ❌ No job queue / async workers — sequential, or a one-shot thread pool at most.
- ❌ No Docker/K8s unless doing the optional Daytona wrapper.
- ❌ No frontend framework / bundler — one static HTML file.
- ❌ No scene-index, embeddings, or vision models in the core path — spoken-word search only.
- ❌ No retries/observability/config systems — fail soft to cached data and move on.
- ✅ Hardcode sensible defaults. ✅ Every external dependency has a cached fallback. ✅ Small, readable functions with docstrings.

---

## 12. Build order (get a working slice fast)

1. `config.py` + `requirements.txt` + `.env.example` + `data/catalog.sample.json`.
2. `video.py` (upload + index + search) — verify search returns shots on the sample.
3. `matcher.py` → one product → a window.
4. `clipper.py` → one clip with overlay + captions → a playable `stream_url`. **(Milestone: one shoppable clip end-to-end.)**
5. `copywriter.py` → hook/caption for that clip.
6. `pipeline.py` + `run.py` → loop ~6 products → `clips.json`.
7. `web/index.html` → gallery renders the clips. **(Milestone: full demo.)**
8. Only then: pick from §10 stretch items if time remains.

Keep each step runnable on its own. Commit after each milestone.
