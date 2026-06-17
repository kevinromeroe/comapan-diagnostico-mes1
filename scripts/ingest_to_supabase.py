#!/usr/bin/env python3
"""Ingester one-shot: carga datasets de Apify + diagnostico.json a Supabase.

Uso (en GitHub Actions):
    python scripts/ingest_to_supabase.py

Env vars requeridas:
    APIFY_TOKEN
    SUPABASE_URL  (ej: https://pmeotakzlgkjdbwdttyf.supabase.co)
    SUPABASE_SERVICE_KEY  (service_role JWT)

Lo que hace:
1. Lee data/diagnostico.json (el baseline). Insert/upsert a Supabase con
   period_id='diagnostico'. Ya existe en periods (seed del schema).
2. Por cada plataforma del periodo 2026-06:
   - Baja el dataset de Apify (sin lanzar actores, solo lee — GRATIS)
   - Normaliza al shape canónico
   - Filtra a calendario mensual (jun 1 – jun 30)
   - Recomputa aggregates
   - Upsertea accounts, posts, aggregates, etc. en Supabase
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, date, timezone
from pathlib import Path

# Forzar PYTHONPATH desde scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.extract.apify_client import ApifyClient
from pipeline.load.supabase_client import Supabase
from pipeline.transform import aggregate, normalize, top_posts
from pipeline.util.config import PROJECT_ROOT, require_env
from pipeline.util.log import get_logger

log = get_logger("ingest")

CLIENT_ID = "comapan"

# Datasets identificados en Apify del run del 17-jun (datasets viven hasta el 24-jun)
DATASETS_JUNIO = {
    "instagram":      "RakR7HO3aDEblf7d1",
    "facebook_pages": "GCHRhiEfWQy6AVReV",
    "facebook_posts": "dhtdlg1vQ57HIefC3",
    "tiktok":         "s7WVGGR04XRaT3Bcf",
    "linkedin":       "OQu7ZSAQO3H8DMX9N",
}


def june_calendar_window() -> tuple[datetime, datetime]:
    """Junio 2026 calendario: 1-jun 00:00 UTC a 30-jun 23:59:59 UTC."""
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def _filter_window(posts: list[dict], start: datetime, end: datetime) -> list[dict]:
    out = []
    for p in posts:
        ts = p.get("timestamp")
        if isinstance(ts, datetime) and start <= ts <= end:
            out.append(p)
    return out


def _platform_aggregates(posts: list[dict]) -> dict:
    """Devuelve un dict {metric_name: metric_value} listo para insertar como
    múltiples rows en la tabla aggregates."""
    return {
        "engagement_stats": aggregate.engagement_stats(posts),
        "by_type":          aggregate.by_type(posts),
        "by_day":           aggregate.by_day_of_week(posts),
        "by_hour":          aggregate.by_hour(posts),
        "by_week":          aggregate.by_week(posts),
        "top_hashtags":     aggregate.top_hashtags(posts, n=10),
        "captions_avg_len": aggregate.captions_avg_len(posts),
        "top5":             top_posts.top_n(posts, n=5),
    }


def _account_row(account: dict, period_id: str, platform: str) -> dict:
    """Convierte un account normalizado (shape DATA accounts.XXX) en row Supabase."""
    def _i(x):
        try: return int(x) if x not in (None, "") else None
        except: return None
    def _b(x):
        if x in (True, "True", "true"): return True
        if x in (False, "False", "false"): return False
        return None
    return {
        "client_id":    CLIENT_ID,
        "period_id":    period_id,
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


def _post_rows(client_id: str, platform: str, posts: list[dict]) -> list[dict]:
    rows = []
    for p in posts:
        ts = p.get("timestamp")
        rows.append({
            "id":          p["id"],
            "client_id":   client_id,
            "platform":    platform,
            "url":         p.get("url") or "",
            "type":        p.get("type"),
            "caption":     p.get("caption"),
            "hashtags":    p.get("hashtags") or [],
            "posted_at":   ts.isoformat() if isinstance(ts, datetime) else None,
            "likes":       p.get("likes", 0),
            "comments":    p.get("comments", 0),
            "shares":      p.get("shares", 0),
            "views":       (p.get("extra") or {}).get("playCount"),
            "engagement":  p.get("engagement", 0),
            "media_url":   p.get("media_url") or None,
            "is_ad":       False,
            "is_pinned":   bool((p.get("extra") or {}).get("isPinned", False)),
            "raw":         {k: v for k, v in p.items() if k != "timestamp"},  # JSONable
        })
    return rows


def _aggregate_rows(period_id: str, platform: str, aggs: dict) -> list[dict]:
    return [
        {
            "client_id":    CLIENT_ID,
            "period_id":    period_id,
            "platform":     platform,
            "metric_name":  name,
            "metric_value": value,
        }
        for name, value in aggs.items()
    ]


# ============================================================
# DIAGNOSTICO: copia el JSON existente directo a aggregates
# ============================================================
def ingest_diagnostico(sb: Supabase) -> None:
    log.info("ingest_diagnostico_start")
    data = json.loads((PROJECT_ROOT / "data" / "diagnostico.json").read_text())

    # Accounts
    for platform_label, account in (data.get("accounts") or {}).items():
        platform = platform_label.lower()
        row = _account_row(account, "diagnostico", platform)
        sb.upsert("accounts", [row], on_conflict="client_id,period_id,platform")

    # Aggregates (de cada plataforma)
    for platform in ("instagram", "facebook", "tiktok", "linkedin"):
        block = data.get(platform) or {}
        if not block:
            continue
        agg_rows = []
        for metric_name in ("by_type","by_day","by_hour","by_week","top_hashtags","top5"):
            if metric_name in block:
                agg_rows.append({
                    "client_id":    CLIENT_ID,
                    "period_id":    "diagnostico",
                    "platform":     platform,
                    "metric_name":  metric_name,
                    "metric_value": block[metric_name],
                })
        for k in ("n_posts","engagement_total","engagement_promedio","engagement_mediana","captions_avg_len"):
            if k in block:
                agg_rows.append({
                    "client_id":    CLIENT_ID,
                    "period_id":    "diagnostico",
                    "platform":     platform,
                    "metric_name":  k,
                    "metric_value": block[k],
                })
        if agg_rows:
            sb.upsert("aggregates", agg_rows,
                      on_conflict="client_id,period_id,platform,metric_name")

    log.info("ingest_diagnostico_done")


# ============================================================
# JUNIO 2026: re-baja datasets de Apify, normaliza, filtra calendario
# ============================================================
def ingest_junio(sb: Supabase) -> None:
    log.info("ingest_junio_start")
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))
    start, end = june_calendar_window()

    period_id = "2026-06"

    # Borrar lo viejo de este periodo (para hacer idempotente)
    for table in ("accounts","aggregates","hallazgos","summaries"):
        try:
            sb.delete(table, f"client_id=eq.{CLIENT_ID}&period_id=eq.{period_id}")
        except Exception as exc:
            log.warning("delete_failed", extra={"table": table, "err": str(exc)})

    platforms_data: dict[str, dict] = {}

    # ---- Instagram ----
    items = apify.dataset_items(DATASETS_JUNIO["instagram"])
    norm = normalize.normalize_instagram(items)
    norm["posts"] = _filter_window(norm["posts"], start, end)
    platforms_data["instagram"] = norm

    # ---- Facebook ----
    page_items = apify.dataset_items(DATASETS_JUNIO["facebook_pages"])
    post_items = apify.dataset_items(DATASETS_JUNIO["facebook_posts"])
    fb_account = normalize.normalize_facebook_page(page_items)
    fb_posts = _filter_window(normalize.normalize_facebook_posts(post_items), start, end)
    platforms_data["facebook"] = {"account": fb_account, "posts": fb_posts}

    # ---- TikTok ----
    items = apify.dataset_items(DATASETS_JUNIO["tiktok"])
    norm = normalize.normalize_tiktok(items)
    norm["posts"] = _filter_window(norm["posts"], start, end)
    platforms_data["tiktok"] = norm

    # ---- LinkedIn ----
    items = apify.dataset_items(DATASETS_JUNIO["linkedin"])
    norm = normalize.normalize_linkedin(items)
    norm["posts"] = _filter_window(norm["posts"], start, end)
    platforms_data["linkedin"] = norm

    # ---- Persistir a Supabase ----
    for platform, block in platforms_data.items():
        if block.get("account"):
            sb.upsert("accounts", [_account_row(block["account"], period_id, platform)],
                      on_conflict="client_id,period_id,platform")
        posts = block.get("posts") or []
        if posts:
            sb.upsert("posts", _post_rows(CLIENT_ID, platform, posts),
                      on_conflict="id")
            aggs = _platform_aggregates(posts)
            sb.upsert("aggregates", _aggregate_rows(period_id, platform, aggs),
                      on_conflict="client_id,period_id,platform,metric_name")
        log.info("platform_ingested",
                 extra={"platform": platform, "n_posts": len(posts)})

    log.info("ingest_junio_done")


def main() -> int:
    sb = Supabase()
    ingest_diagnostico(sb)
    ingest_junio(sb)
    print("\n✓ Ingest completo. Verifica en Supabase Table Editor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
