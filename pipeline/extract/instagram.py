"""Extractor de Instagram — lanza el actor Apify on-demand y normaliza."""
from __future__ import annotations

from typing import Any

from pipeline.extract.apify_client import ApifyClient
from pipeline.transform.normalize import normalize_instagram
from pipeline.util.log import get_logger

log = get_logger(__name__)


def extract(client: ApifyClient, platform_cfg: dict[str, Any]) -> dict[str, Any]:
    actor_id = platform_cfg["apify"]["actor_id"]
    actor_input = platform_cfg["apify"].get("input") or {}
    items = client.run_actor_sync(actor_id, actor_input)
    log.info("instagram_extracted", extra={"items": len(items)})
    return normalize_instagram(items)
