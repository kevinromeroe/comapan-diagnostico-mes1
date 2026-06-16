"""Extractor de Facebook — orquesta 2 actores (page + posts) y combina."""
from __future__ import annotations

from typing import Any

from pipeline.extract.apify_client import ApifyClient
from pipeline.transform.normalize import normalize_facebook_page, normalize_facebook_posts
from pipeline.util.log import get_logger

log = get_logger(__name__)


def extract(client: ApifyClient, platform_cfg: dict[str, Any]) -> dict[str, Any]:
    page_actor = platform_cfg["apify"]["page"]["actor_id"]
    posts_actor = platform_cfg["apify"]["posts"]["actor_id"]

    page_account: dict[str, Any] = {}
    posts: list[dict[str, Any]] = []

    page_run = client.last_succeeded_run_for_actor(page_actor)
    if page_run:
        page_items = client.dataset_items(page_run["defaultDatasetId"])
        page_account = normalize_facebook_page(page_items)
    else:
        log.warning("facebook_page_no_run", extra={"actor_id": page_actor})

    posts_run = client.last_succeeded_run_for_actor(posts_actor)
    if posts_run:
        post_items = client.dataset_items(posts_run["defaultDatasetId"])
        posts = normalize_facebook_posts(post_items)
    else:
        log.warning("facebook_posts_no_run", extra={"actor_id": posts_actor})

    log.info("facebook_extracted", extra={"posts": len(posts)})
    return {"account": page_account, "posts": posts}
