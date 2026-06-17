"""Extractor de TikTok — usa el actor de posts (incluye perfil embebido)."""
from __future__ import annotations

from typing import Any

from pipeline.extract.apify_client import ApifyClient
from pipeline.transform.normalize import normalize_tiktok
from pipeline.util.log import get_logger

log = get_logger(__name__)


def extract(client: ApifyClient, platform_cfg: dict[str, Any]) -> dict[str, Any]:
    posts_cfg = platform_cfg["apify"]["posts"]
    items = client.run_actor_sync(posts_cfg["actor_id"], posts_cfg.get("input") or {})
    log.info("tiktok_extracted", extra={"items": len(items)})
    return normalize_tiktok(items)
