"""Ensambla el objeto DATA canónico (v1.0.0) listo para inyectar al template HTML.

Recibe los resultados de normalize por plataforma + ventana + agency,
devuelve el dict que el template consume tal cual.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from pipeline.transform import aggregate, top_posts
from pipeline.transform.insights_llm import generate_insights
from pipeline.util.log import get_logger

log = get_logger(__name__)


def filter_in_window(posts: list[dict[str, Any]], window_start: datetime) -> list[dict[str, Any]]:
    """Conserva solo posts con timestamp dentro de la ventana de análisis."""
    out = []
    for p in posts:
        ts = p.get("timestamp")
        if isinstance(ts, datetime) and ts >= window_start:
            out.append(p)
    return out


def platform_block(posts: list[dict[str, Any]], n_top: int = 5, n_hashtags: int = 10) -> dict[str, Any]:
    """Calcula todos los aggregates + top + hashtags para una plataforma."""
    stats = aggregate.engagement_stats(posts)
    return {
        **stats,
        "by_type": aggregate.by_type(posts),
        "by_day": aggregate.by_day_of_week(posts),
        "by_hour": aggregate.by_hour(posts),
        "by_week": aggregate.by_week(posts),
        "top_hashtags": aggregate.top_hashtags(posts, n=n_hashtags),
        "captions_avg_len": aggregate.captions_avg_len(posts),
        "top5": top_posts.top_n(posts, n=n_top),
    }


def assemble(
    normalized: dict[str, dict[str, Any]],
    *,
    window_days: int = 90,
    n_top: int = 5,
    n_hashtags: int = 10,
    snapshot_dt: datetime | None = None,
    with_llm_insights: bool = True,
    llm_model: str = "claude-sonnet-4-6",
) -> dict[str, Any]:
    """
    `normalized` viene como:
        {
            "instagram": {"account": {...}, "posts": [...]},
            "facebook":  {"account": {...}, "posts": [...]},
            "tiktok":    {"account": {...}, "posts": [...]},
            "linkedin":  {"account": {...}, "posts": [...]},
        }
    """
    snapshot_dt = snapshot_dt or datetime.now(timezone.utc)
    window_start = snapshot_dt - timedelta(days=window_days)

    # Filtrar posts a la ventana
    posts_by_platform = {
        plat: filter_in_window(normalized.get(plat, {}).get("posts", []), window_start)
        for plat in ("instagram", "facebook", "tiktok", "linkedin")
    }

    # Track Facebook posts sin fecha (caveat documentado en docs/apify_schemas/facebook.md)
    fb_raw = normalized.get("facebook", {}).get("posts", [])
    fb_undated = sum(1 for p in fb_raw if not p.get("timestamp"))
    fb_total = len(fb_raw)

    # accounts
    accounts = {
        "Instagram": normalized.get("instagram", {}).get("account", {}),
        "Facebook":  normalized.get("facebook", {}).get("account", {}),
        "TikTok":    normalized.get("tiktok", {}).get("account", {}),
        "LinkedIn":  normalized.get("linkedin", {}).get("account", {}),
    }

    # bloques por plataforma
    blocks = {
        plat: platform_block(posts_by_platform[plat], n_top=n_top, n_hashtags=n_hashtags)
        for plat in posts_by_platform
    }

    # consolidated: una fila por plataforma
    def _consolidated_row(plat: str, label: str) -> dict[str, Any]:
        block = blocks[plat]
        top = (block["top5"] or [{}])[0] if block["top5"] else {}
        return {
            "plataforma": label,
            "username": accounts[label].get("username", ""),
            "seguidores": accounts[label].get("seguidores", ""),
            "posts_90d": str(block["n_posts"]),
            "engagement_total_90d": str(block["engagement_total"]),
            "engagement_promedio_post": str(block["engagement_promedio"]),
            "top_post_url": top.get("url", ""),
            "top_post_engagement": str(top.get("engagement", "")),
            "snapshot_fecha": accounts[label].get("snapshot_fecha", snapshot_dt.date().isoformat()),
        }

    consolidated = [
        _consolidated_row("instagram", "Instagram"),
        _consolidated_row("facebook", "Facebook"),
        _consolidated_row("tiktok", "TikTok"),
        _consolidated_row("linkedin", "LinkedIn"),
    ]

    # snapshots_history: una fila por métrica relevante
    snapshots_history: list[dict[str, Any]] = []
    snap_date = snapshot_dt.date().isoformat()
    for label, key in [
        ("Instagram", "followers"),
        ("Facebook", "page_likes"),
        ("LinkedIn", "followers"),
    ]:
        acc = accounts[label]
        value = acc.get("seguidores") if key == "followers" else acc.get("page_likes")
        if value:
            snapshots_history.append({
                "snapshot_date": snap_date,
                "plataforma": label,
                "metrica": key,
                "valor": str(value),
                "posts_acumulados": acc.get("posts_totales", ""),
                "fuente": "apify",
            })

    payload = {
        "generated_at": snapshot_dt.strftime("%d/%m/%Y"),
        "ventana": {
            "desde": window_start.date().isoformat(),
            "hasta": snapshot_dt.date().isoformat(),
        },
        "accounts": accounts,
        "consolidated": consolidated,
        "instagram": blocks["instagram"],
        "facebook": blocks["facebook"],
        "tiktok": blocks["tiktok"],
        "linkedin": blocks["linkedin"],
        "fb_undated": fb_undated,
        "fb_total": fb_total,
        "snapshots_history": snapshots_history,
    }

    # Hallazgos LLM al final — alimentamos a Claude con el payload completo
    if with_llm_insights:
        payload["hallazgos_llm"] = generate_insights(payload, model=llm_model)

    return payload
