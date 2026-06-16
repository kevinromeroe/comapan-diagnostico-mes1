"""Extractor de LinkedIn — `harvestapi/linkedin-company-posts`."""
from __future__ import annotations

from typing import Any

from pipeline.extract.apify_client import ApifyClient
from pipeline.transform.normalize import normalize_linkedin
from pipeline.util.log import get_logger

log = get_logger(__name__)


def extract(client: ApifyClient, platform_cfg: dict[str, Any]) -> dict[str, Any]:
    actor_id = platform_cfg["apify"]["actor_id"]
    run = client.last_succeeded_run_for_actor(actor_id)
    if not run:
        log.warning("linkedin_no_recent_run", extra={"actor_id": actor_id})
        return {"account": {}, "posts": []}
    items = client.dataset_items(run["defaultDatasetId"])
    log.info("linkedin_extracted", extra={"items": len(items)})
    return normalize_linkedin(items)
