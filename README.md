# ClipCart

Turn live-selling videos into shoppable vertical clips — automatically.

ClipCart takes a live-stream recording and a product catalog, locates each product's on-screen moment via spoken-word search, cuts a vertical clip around it, and generates social copy (hook, caption, hashtags) ready for posting.

## How it works

```
catalog.json + video
       |
       v
1. Load catalog          — JSON file or BrightData-scraped Shopee store
2. Upload & index video  — VideoDB transcribes and indexes the stream
3. Match product window  — spoken-word search + optional Kimi vision verification
4. Build clip            — VideoDB cuts the vertical clip and returns a stream URL
5. Generate copy         — Kimi writes hook, caption, and hashtags per product
       |
       v
output/clips.json        — gallery-ready records with stream URLs and copy
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for package management
- API keys for [VideoDB](https://videodb.io), [Moonshot/Kimi](https://platform.moonshot.cn), and optionally [BrightData](https://brightdata.com)

## Setup

```bash
# clone and install dependencies
git clone <repo-url>
cd clipcart
uv sync

# copy the env template and fill in your keys
cp .env.example .env
```

`.env` fields:

| Variable | Required | Description |
|---|---|---|
| `VIDEO_DB_API_KEY` | Yes | VideoDB API key |
| `MOONSHOT_API_KEY` | Yes | Kimi (Moonshot) API key for image verification and copywriting |
| `BRIGHTDATA_API_TOKEN` | No | BrightData token for live catalog scraping |
| `BRIGHTDATA_ZONE` | No | BrightData zone (default: `web_unlocker`) |
| `SHOPEE_STORE_URL` | No | Shopee store URL to scrape |

## Usage

### CLI

```bash
# run with defaults (data/the_style_soiree_live.mp4 + data/catalog.sample.json)
uv run python -m clipcart.run

# specify a video and catalog
uv run python -m clipcart.run --video path/to/video.mp4 --catalog data/catalog.sample.json

# limit to 3 products, skip image verification
uv run python -m clipcart.run --limit 3 --no-image-verify
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--video` | `data/the_style_soiree_live.mp4` | URL or local path to the source video |
| `--catalog` | `data/catalog.sample.json` | Path to the product catalog JSON |
| `--limit` | `6` | Max number of products to process |
| `--out` | `output/clips.json` | Output path for the clips JSON |
| `--no-image-verify` | off | Disable Kimi vision shot verification |
| `--log-level` | `INFO` | Logging verbosity |

### Web UI

```bash
uv run python web/server.py
# open http://localhost:5000
```

The web server exposes the pipeline via a REST API and serves a gallery UI:

- `GET /api/clips` — returns the current `output/clips.json`
- `GET /api/status` — pipeline status (`idle` / `running` / `done` / `error`)
- `POST /api/run` — start the pipeline (`{ video_source, limit, no_image_verify }`)

## Output format

Each record in `output/clips.json`:

```json
{
  "name": "Floral Wrap Dress",
  "price": "SGD 29.90",
  "buy_url": "https://...",
  "image_url": "https://...",
  "hook": "This dress sold out in 10 minutes last week...",
  "caption": "The floral wrap dress everyone is talking about...",
  "hashtags": ["#LiveShopping", "#FashionFinds"],
  "schedule": 24,
  "stream_url": "https://stream.videodb.io/...",
  "start": 142.5,
  "end": 172.5
}
```

## Project structure

```
clipcart/
  catalog.py       — load and parse the product catalog
  matcher.py       — match products to video windows via spoken-word search
  clipper.py       — build clips via VideoDB
  copywriter.py    — generate social copy with Kimi
  image_verify.py  — Kimi vision frame verification
  video.py         — VideoDB connection and upload helpers
  pipeline.py      — full pipeline orchestrator
  run.py           — CLI entry point
  config.py        — env vars and pipeline constants

web/
  server.py        — Flask dev server
  index.html       — gallery UI

scripts/
  scrape_catalog.py — BrightData-based Shopee catalog scraper

data/              — sample video and catalog (not committed)
output/            — generated clips.json (not committed)
```

## Catalog JSON format

```json
[
  {
    "name": "Floral Wrap Dress",
    "price": "SGD 29.90",
    "buy_url": "https://shopee.sg/...",
    "image_url": "https://..."
  }
]
```
