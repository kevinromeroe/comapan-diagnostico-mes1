#!/usr/bin/env python3
"""One-shot: corre el actor de LinkedIn con el input CORREGIDO y carga a Supabase
SOLO para LinkedIn del periodo 2026-06.

Costo: ~$0.02 USD (Apify cobra $0.002/post + $0.00005 start).
No toca las otras plataformas — su data en Supabase queda intacta.

Uso (en workflow):
    python scripts/ingest_linkedin_only.py
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

log = get_logger("ingest-linkedin")
CLIENT_ID = "comapan"
PERIOD_ID = "2026-06"


def june_window() -> tuple[datetime, datetime]:
    return (datetime(2026, 6, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc))


def _filter(posts: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [p for p in posts
            if isinstance(p.get("timestamp"), datetime) and start <= p["timestamp"] <= end]


def _account_row(account: dict, platform: str) -> dict:
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
        "platform":     platform,
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
        "page_likes":   _i(account.get("page_likes")),
        "views_window": _i(account.get("views_totales_90d")),
        "rating":       account.get("rating") or None,
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
            "platform":   "linkedin",
            "url":        p.get("url") or "",
            "type":       p.get("type"),
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
    cfg = load_client(CLIENT_ID)["platforms"]["linkedin"]
    sb = Supabase()
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))

    start, end = june_window()

    # Borrar lo viejo de LinkedIn en 2026-06 (idempotente)
    try:
        sb.delete("accounts", f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}&platform=eq.linkedin")
        sb.delete("aggregates", f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}&platform=eq.linkedin")
    except Exception as exc:
        log.warning("delete_old_linkedin_failed", extra={"err": str(exc)})

    # Correr el actor con el input nuevo
    # harvestapi/linkedin-company-posts es PAY_PER_EVENT — Apify exige cap explícito
    print("→ Lanzando actor LinkedIn con input corregido…")
    items = apify.run_actor_sync(
        cfg["apify"]["actor_id"],
        cfg["apify"]["input"],
        max_total_charge_usd=0.50,   # cap = $0.50, sobrado para ~100 posts a $0.002 c/u
    )
    print(f"  Actor retornó {len(items)} posts crudos")

    if not items:
        print("⚠️  El actor seguía devolviendo 0 items. Revisar input o LinkedIn cambió algo.")
        return 1

    norm = normalize.normalize_linkedin(items)
    filtered = _filter(norm["posts"], start, end)
    print(f"  Posts en ventana junio (1-30): {len(filtered)} de {len(norm['posts'])} totales")

    # Cuenta
    if norm.get("account"):
        sb.upsert("accounts", [_account_row(norm["account"], "linkedin")],
                  on_conflict="client_id,period_id,platform")
        print(f"  ✓ Account upserted (followers: {norm['account'].get('seguidores')})")

    # Posts
    if filtered:
        sb.upsert("posts", _post_rows(filtered), on_conflict="id")
        print(f"  ✓ {len(filtered)} posts upserted")

        # Aggregates
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
            "platform":     "linkedin",
            "metric_name":  name,
            "metric_value": value,
        } for name, value in aggs.items()]
        sb.upsert("aggregates", rows, on_conflict="client_id,period_id,platform,metric_name")
        print(f"  ✓ {len(rows)} aggregates upserted")

    print("\n✅ LinkedIn ingested. Re-corre el workflow 'Generate Narratives' para refrescar")
    print("   los headlines y chart_insights de LinkedIn con la data real.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
