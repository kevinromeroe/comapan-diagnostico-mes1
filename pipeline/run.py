"""Orquestador principal del pipeline.

Uso:
    python -m pipeline.run --client comapan
    python -m pipeline.run --client comapan --period 2026-06-15 --dry-run
    python -m pipeline.run --client comapan --no-publish     # extract+render, no push
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone, date

from pipeline.extract import facebook, instagram, linkedin, tiktok
from pipeline.extract.apify_client import ApifyClient
from pipeline.load import json_writer, thumbs
from pipeline.notify import email as notify_email
from pipeline.publish import git as publish_git
from pipeline.render import build as render_build
from pipeline.transform.assemble import assemble
from pipeline.util.config import load_client, load_global, require_env
from pipeline.util.log import get_logger

log = get_logger("pipeline.run")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True, help="ID del cliente (ej: comapan)")
    parser.add_argument("--period", help="Fecha del snapshot YYYY-MM-DD (default: hoy)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Sin descarga de thumbs ni publish ni notify")
    parser.add_argument("--no-publish", action="store_true",
                        help="Hace render local pero no git push")
    parser.add_argument("--no-notify", action="store_true",
                        help="No envía notificación final")
    args = parser.parse_args()

    started_at = time.time()
    global_cfg = load_global()
    client_cfg = load_client(args.client)
    log.info("run_start", extra={"client": args.client, "dry_run": args.dry_run})

    snap_dt = (
        datetime.combine(date.fromisoformat(args.period), datetime.min.time(),
                         tzinfo=timezone.utc)
        if args.period
        else datetime.now(timezone.utc)
    )

    # =====================  EXTRACT  =====================
    apify_token = require_env("APIFY_TOKEN")
    client = ApifyClient(
        token=apify_token,
        max_attempts=global_cfg.get("pipeline", {}).get("retries", {}).get("max_attempts", 3),
        backoff_seconds=global_cfg.get("pipeline", {}).get("retries", {}).get("backoff_seconds"),
        timeout=global_cfg.get("pipeline", {}).get("timeouts", {}).get("apify_dataset_fetch", 60),
    )

    platforms_cfg = client_cfg["platforms"]
    extractors = {
        "instagram": instagram,
        "facebook": facebook,
        "tiktok": tiktok,
        "linkedin": linkedin,
    }

    normalized: dict[str, dict] = {}
    platform_status: dict[str, dict] = {}
    for name, module in extractors.items():
        cfg = platforms_cfg.get(name, {})
        if not cfg.get("enabled"):
            log.info("platform_skipped", extra={"platform": name})
            platform_status[name] = {"status": "skipped", "n_posts": 0}
            continue
        try:
            normalized[name] = module.extract(client, cfg)
            platform_status[name] = {
                "status": "ok",
                "n_posts": len(normalized[name].get("posts", [])),
            }
        except Exception as exc:
            log.error("platform_extract_failed", extra={"platform": name, "error": str(exc)})
            normalized[name] = {"account": {}, "posts": []}
            platform_status[name] = {"status": "error", "n_posts": 0, "error": str(exc)}

    # =====================  TRANSFORM  =====================
    window_days = client_cfg.get("client", {}).get("window_days", 90)
    n_top = client_cfg.get("analytics", {}).get("top_posts_n", 5)
    n_tags = client_cfg.get("analytics", {}).get("top_hashtags_n", 10)
    data = assemble(
        normalized, window_days=window_days, n_top=n_top, n_hashtags=n_tags, snapshot_dt=snap_dt,
    )

    # =====================  LOAD  =====================
    if not args.dry_run:
        thumbs.replace_top5_media(data)
    data_path = json_writer.write_data(data, snap_dt.date())

    # =====================  RENDER  =====================
    if not args.dry_run:
        render_build.build(data_path=data_path)

    # =====================  PUBLISH  =====================
    commit_sha: str | None = None
    if not args.dry_run and not args.no_publish:
        cycle = client_cfg.get("client", {}).get("cycle", "quincenal")
        try:
            published = publish_git.commit_report(snap_dt.date(), cycle=cycle)
            commit_sha = "pushed" if published else "no_changes"
        except Exception as exc:
            log.error("publish_failed", extra={"error": str(exc)})
            commit_sha = f"error: {exc}"

    # =====================  NOTIFY  =====================
    duration = round(time.time() - started_at, 1)
    summary = {
        "client": client_cfg.get("client", {}).get("name", args.client),
        "period": snap_dt.date().isoformat(),
        "duration_seconds": duration,
        "platforms": platform_status,
        "commit_sha": commit_sha or "skipped",
        "url": f"https://{client_cfg['client']['deploy']['domain']}",
    }

    if not args.dry_run and not args.no_notify:
        notif_cfg = client_cfg.get("notifications", {}).get("email", {})
        if notif_cfg.get("enabled"):
            statuses = [v.get("status") for v in platform_status.values()]
            run_status = "error" if "error" in statuses else (
                "warning" if "warning" in statuses else "ok"
            )
            subject = notify_email.build_subject(
                summary["client"],
                notif_cfg.get("subject_prefix", "[Datalitica]"),
                run_status,
            )
            notify_email.send(summary, to=notif_cfg.get("to", []), subject=subject)

    log.info("run_done", extra=summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
