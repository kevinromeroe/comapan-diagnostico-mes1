"""Extractor de Facebook — lanza 2 actores (page + posts) on-demand."""
from __future__ import annotations

from typing import Any

from pipeline.extract.apify_client import ApifyClient
from pipeline.transform.normalize import normalize_facebook_page, normalize_facebook_posts
from pipeline.util.log import get_logger

log = get_logger(__name__)


def extract(client: ApifyClient, platform_cfg: dict[str, Any]) -> dict[str, Any]:
    page_cfg = platform_cfg["apify"]["page"]
    posts_cfg = platform_cfg["apify"]["posts"]

    page_account: dict[str, Any] = {}
    posts: list[dict[str, Any]] = []

    try:
        page_items = client.run_actor_sync(page_cfg["actor_id"], page_cfg.get("input") or {})
        page_account = normalize_facebook_page(page_items)
    except Exception as exc:
        log.error("facebook_page_failed", extra={"error": str(exc)})

    try:
        post_items = client.run_actor_sync(posts_cfg["actor_id"], posts_cfg.get("input") or {})
        posts = normalize_facebook_posts(post_items)
    except Exception as exc:
        log.error("facebook_posts_failed", extra={"error": str(exc)})

    log.info("facebook_extracted", extra={"posts": len(posts)})
    return {"account": page_account, "posts": posts}
