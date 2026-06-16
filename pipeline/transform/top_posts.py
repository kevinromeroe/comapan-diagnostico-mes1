"""Selección y formato del top N posts por engagement."""
from __future__ import annotations

from datetime import datetime
from typing import Any


CAPTION_TRUNCATE_AT = 150


def top_n(posts: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    """Ordena posts desc por engagement (desempata por likes, luego fecha desc)."""

    def sort_key(p: dict[str, Any]) -> tuple:
        ts = p.get("timestamp") or datetime.min
        return (-p["engagement"], -p["likes"], -ts.timestamp() if isinstance(ts, datetime) else 0)

    sorted_posts = sorted(posts, key=sort_key)
    return [_format(p) for p in sorted_posts[:n]]


def _format(p: dict[str, Any]) -> dict[str, Any]:
    ts = p.get("timestamp")
    fecha = ts.date().isoformat() if isinstance(ts, datetime) else ""
    caption = p.get("caption") or ""
    if len(caption) > CAPTION_TRUNCATE_AT:
        caption = caption[: CAPTION_TRUNCATE_AT - 1] + "…"
    return {
        "fecha": fecha,
        "tipo": p.get("type", ""),
        "url": p.get("url", ""),
        "media_url": p.get("media_url", "") or "",   # se reemplaza por path local en load.thumbs
        "caption": caption,
        "engagement": p["engagement"],
        "likes": p["likes"],
        "comentarios": p["comments"],
    }
