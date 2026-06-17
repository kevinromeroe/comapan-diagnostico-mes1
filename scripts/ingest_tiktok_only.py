#!/usr/bin/env python3
"""One-shot: ingestar SOLO TikTok para el periodo 2026-06.

Costo estimado: ~$0.05-0.15 USD (clockworks/tiktok-scraper).
No toca las otras plataformas — su data en Supabase queda intacta.

Uso (en workflow):
    python scripts/ingest_tiktok_only.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.extract.apify_client import ApifyClient
from pipeline.load.supabase_client import Supabase
from pipeline.transform import aggregate, normalize, top_posts
from pipeline.util.config import load_client, require_env
from pipeline.util.log import get_logger

log = get_logger("ingest-tiktok")
CLIENT_ID = "comapan"
PERIOD_ID = "2026-06"


def june_window() -> tuple[datetime, datetime]:
    return (datetime(2026, 6, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc))


def _filter(posts: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [p for p in posts
            if isinstance(p.get("timestamp"), datetime) and start <= p["timestamp"] <= end]


def _account_row(account: dict) -> dict:
    def _i(x):
        try: return int(x) if x not in (None, "") else None
        except: return None
    def _b(x):
        if x in (True, "True", "true"): return True
        if x in (False, "False", "false"): return False
        return None
    return {
        "client_id":    CLIENT_ID,
        "period_id":    PERIOD_ID,
        "platform":     "tiktok",
        "username":     account.get("username") or None,
        "display_name": account.get("nombre") or None,
        "bio":          account.get("bio") or None,
        "followers":    _i(account.get("seguidores")),
        "following_n":  _i(account.get("siguiendo")),
        "posts_total":  _i(account.get("posts_totales")),
        "verified":     _b(account.get("verified")),
        "is_business":  _b(account.get("business_account")),
        "category":     account.get("categoria") or None,
        "website":      account.get("website") or None,
        "external_url": account.get("url_externa") or None,
        "views_window": _i(account.get("views_totales_90d")),
        "raw":          account,
        "snapshot_at":  account.get("snapshot_fecha") or None,
    }


def _post_rows(posts: list[dict]) -> list[dict]:
    rows = []
    for p in posts:
        ts = p.get("timestamp")
        rows.append({
            "id":         p["id"],
            "client_id":  CLIENT_ID,
            "platform":   "tiktok",
            "url":        p.get("url") or "",
            "type":       p.get("type") or "Video",
            "caption":    p.get("caption"),
            "hashtags":   p.get("hashtags") or [],
            "posted_at":  ts.isoformat() if isinstance(ts, datetime) else None,
            "likes":      p.get("likes", 0),
            "comments":   p.get("comments", 0),
            "shares":     p.get("shares", 0),
            "engagement": p.get("engagement", 0),
            "media_url":  p.get("media_url") or None,
            "is_ad":      False,
            "is_pinned":  False,
            "raw":        {k: v for k, v in p.items() if k != "timestamp"},
        })
    return rows


def main() -> int:
    cfg = load_client(CLIENT_ID)["platforms"]["tiktok"]
    sb = Supabase()
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))

    start, end = june_window()

    # Borrar lo viejo de TikTok en 2026-06 (idempotente)
    try:
        sb.delete("accounts", f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}&platform=eq.tiktok")
        sb.delete("aggregates", f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}&platform=eq.tiktok")
    except Exception as exc:
        log.warning("delete_old_tiktok_failed", extra={"err": str(exc)})

    # Profile metadata
    print("→ Lanzando actor TikTok profile (seguidores)…")
    profile_items = apify.run_actor_sync(
        cfg["apify"]["profile"]["actor_id"],
        cfg["apify"]["profile"]["input"],
        max_total_charge_usd=0.20,
    )
    print(f"  Profile actor retornó {len(profile_items)} items")

    # Posts
    print("→ Lanzando actor TikTok posts (videos)…")
    items = apify.run_actor_sync(
        cfg["apify"]["posts"]["actor_id"],
        cfg["apify"]["posts"]["input"],
        max_total_charge_usd=0.30,
    )
    print(f"  Posts actor retornó {len(items)} videos crudos")

    if not items and not profile_items:
        print("⚠️  Ambos actores devolvieron 0. Revisar input.")
        return 1

    norm = normalize.normalize_tiktok(items, profile_items)
    filtered = _filter(norm["posts"], start, end)
    print(f"  Videos en ventana junio (1-30): {len(filtered)} de {len(norm['posts'])} totales")

    if norm.get("account"):
        sb.upsert("accounts", [_account_row(norm["account"])],
                  on_conflict="client_id,period_id,platform")
        print(f"  ✓ Account upserted (followers: {norm['account'].get('seguidores')})")

    if filtered:
        sb.upsert("posts", _post_rows(filtered), on_conflict="id")
        print(f"  ✓ {len(filtered)} posts upserted")

        aggs = {
            "engagement_stats": aggregate.engagement_stats(filtered),
            "by_type":          aggregate.by_type(filtered),
            "by_day":           aggregate.by_day_of_week(filtered),
            "by_hour":          aggregate.by_hour(filtered),
            "by_week":          aggregate.by_week(filtered),
            "top_hashtags":     aggregate.top_hashtags(filtered, n=10),
            "captions_avg_len": aggregate.captions_avg_len(filtered),
            "top5":             top_posts.top_n(filtered, n=5),
        }
        rows = [{
            "client_id":    CLIENT_ID,
            "period_id":    PERIOD_ID,
            "platform":     "tiktok",
            "metric_name":  name,
            "metric_value": value,
        } for name, value in aggs.items()]
        sb.upsert("aggregates", rows, on_conflict="client_id,period_id,platform,metric_name")
        print(f"  ✓ {len(rows)} aggregates upserted")
    else:
        print("  Sin posts en junio. Aggregates no creados (LinkedIn/TT puede no haber publicado en junio).")

    print("\n✅ TikTok ingested. Re-corre 'Generate Narratives' para refrescar hallazgos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
