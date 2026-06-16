"""Orquestador principal del pipeline.

Uso:
    python -m pipeline.run --client comapan
    python -m pipeline.run --client comapan --period 2026-06-15 --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, date

from pipeline.extract import facebook, instagram, linkedin, tiktok
from pipeline.extract.apify_client import ApifyClient
from pipeline.load import json_writer, thumbs
from pipeline.transform.assemble import assemble
from pipeline.util.config import load_client, load_global, require_env
from pipeline.util.log import get_logger

log = get_logger("pipeline.run")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True, help="ID del cliente (ej: comapan)")
    parser.add_argument("--period", help="Fecha del snapshot YYYY-MM-DD (default: hoy)")
    parser.add_argument("--dry-run", action="store_true", help="No descarga thumbs ni publica")
    args = parser.parse_args()

    global_cfg = load_global()
    client_cfg = load_client(args.client)
    log.info("run_start", extra={"client": args.client, "dry_run": args.dry_run})

    snap_dt = (
        datetime.combine(date.fromisoformat(args.period), datetime.min.time(), tzinfo=timezone.utc)
        if args.period
        else datetime.now(timezone.utc)
    )

    apify_token = require_env("APIFY_TOKEN")
    client = ApifyClient(
        token=apify_token,
        max_attempts=global_cfg.get("pipeline", {}).get("retries", {}).get("max_attempts", 3),
        backoff_seconds=global_cfg.get("pipeline", {}).get("retries", {}).get("backoff_seconds"),
        timeout=global_cfg.get("pipeline", {}).get("timeouts", {}).get("apify_dataset_fetch", 60),
    )

    platforms_cfg = client_cfg["platforms"]
    normalized: dict[str, dict] = {}

    extractors = {
        "instagram": instagram,
        "facebook": facebook,
        "tiktok": tiktok,
        "linkedin": linkedin,
    }

    for name, module in extractors.items():
        cfg = platforms_cfg.get(name, {})
        if not cfg.get("enabled"):
            log.info("platform_skipped", extra={"platform": name})
            continue
        try:
            normalized[name] = module.extract(client, cfg)
        except Exception as exc:
            log.error("platform_extract_failed", extra={"platform": name, "error": str(exc)})
            normalized[name] = {"account": {}, "posts": []}

    window_days = client_cfg.get("client", {}).get("window_days", 90)
    n_top = client_cfg.get("analytics", {}).get("top_posts_n", 5)
    n_tags = client_cfg.get("analytics", {}).get("top_hashtags_n", 10)
    data = assemble(
        normalized,
        window_days=window_days,
        n_top=n_top,
        n_hashtags=n_tags,
        snapshot_dt=snap_dt,
    )

    if not args.dry_run:
        thumbs.replace_top5_media(data)

    # Persistir el JSON (gitignored)
    json_writer.write_data(data, snap_dt.date())

    log.info(
        "run_done",
        extra={
            "platforms": {p: len(normalized[p].get("posts", [])) for p in normalized},
            "snapshot": snap_dt.date().isoformat(),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
