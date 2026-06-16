"""Extractor de TikTok — usa `clockworks/tiktok-scraper` (incluye perfil embebido)."""
from __future__ import annotations

from typing import Any

from pipeline.extract.apify_client import ApifyClient
from pipeline.transform.normalize import normalize_tiktok
from pipeline.util.log import get_logger

log = get_logger(__name__)


def extract(client: ApifyClient, platform_cfg: dict[str, Any]) -> dict[str, Any]:
    # Preferimos el de posts (incluye authorMeta). El profile actor queda redundante.
    posts_actor = platform_cfg["apify"]["posts"]["actor_id"]
    run = client.last_succeeded_run_for_actor(posts_actor)
    if not run:
        log.warning("tiktok_no_recent_run", extra={"actor_id": posts_actor})
        return {"account": {}, "posts": []}
    items = client.dataset_items(run["defaultDatasetId"])
    log.info("tiktok_extracted", extra={"items": len(items)})
    return normalize_tiktok(items)
