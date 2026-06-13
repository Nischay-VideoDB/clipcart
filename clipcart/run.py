"""CLI entry point for the ClipCart pipeline.

Usage:
    python -m clipcart.run
    python -m clipcart.run --video path/to/video.mp4 --catalog data/catalog.sample.json
    python -m clipcart.run --video https://example.com/video.mp4 --limit 3
"""

import argparse
import logging

from clipcart import config
from clipcart.pipeline import run


def main() -> None:
    """Parse CLI arguments and run the pipeline."""
    parser = argparse.ArgumentParser(
        description="ClipCart: turn a live-selling video into shoppable clips."
    )
    parser.add_argument(
        "--video",
        default=config.SAMPLE_VIDEO_SOURCE,
        help="URL or local file path to the source video (default: SAMPLE_VIDEO_SOURCE in config).",
    )
    parser.add_argument(
        "--catalog",
        default=config.SAMPLE_CATALOG_PATH,
        help="Path to the product catalog JSON (default: data/catalog.sample.json).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=config.DEFAULT_LIMIT,
        help="Max number of products to process (default: 6).",
    )
    parser.add_argument(
        "--out",
        default="output/clips.json",
        help="Output path for the clips JSON (default: output/clips.json).",
    )
    parser.add_argument(
        "--no-image-verify",
        action="store_true",
        help="Disable Kimi image verification for shot selection.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s  %(name)s  %(message)s",
    )

    run(
        video_source=args.video,
        catalog_path=args.catalog,
        limit=args.limit,
        out_path=args.out,
        use_image_verify=not args.no_image_verify,
    )


if __name__ == "__main__":
    main()
