#!/usr/bin/env python3
"""Ingester DIAGNÓSTICO AMPLIADO: lanza los 4 actores con resultsLimit=300
para tratar de capturar TODA la actividad Ene 1 - May 31, 2026.

Persiste en Supabase con period_id='diagnostico-extendido' (NO sobreescribe
el diagnóstico actual que ya está en producción).

Costo esperado: ~$2.24 USD. Cap total absoluto: ~$3.40 USD.

CAPS por actor (max_total_charge_usd):
    Instagram:           $1.00
    Facebook page:       $0.20
    Facebook posts:      $0.60
    TikTok profile:      $0.20
    TikTok posts:        $0.50
    LinkedIn:            $0.90

Uso (en workflow):
    python scripts/ingest_diagnostico_ampliado.py
"""
from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.extract.apify_client import ApifyClient
from pipeline.load.supabase_client import Supabase
from pipeline.transform import normalize
from pipeline.util.config import load_client, require_env
from pipeline.util.log import get_logger

from scripts.ingest_to_supabase import (
    _filter_window, _platform_aggregates,
    _account_row, _post_rows, _aggregate_rows,
)

log = get_logger("ingest-diag-ampliado")
CLIENT_ID = "comapan"
PERIOD_ID = "diagnostico-extendido"

CAPS = {
    "instagram":      1.00,
    "facebook_page":  0.20,
    "facebook_posts": 0.60,
    "tiktok_profile": 0.20,
    "tiktok_posts":   0.50,
    "linkedin":       0.90,
}

RESULTS_LIMIT = 300


def ventana_ene_may() -> tuple[datetime, datetime]:
    return (datetime(2026, 1, 1,  tzinfo=timezone.utc),
            datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc))


def months_distribution(posts: list[dict]) -> str:
    """Distribución posts por mes — para diagnosticar profundidad real."""
    by_month: dict[str, int] = {}
    for p in posts:
        ts = p.get("timestamp")
        if isinstance(ts, datetime):
            key = f"{ts.year}-{ts.month:02d}"
            by_month[key] = by_month.get(key, 0) + 1
    if not by_month:
        return "(sin posts en ventana)"
    return " · ".join(f"{m}: {n}" for m, n in sorted(by_month.items()))


def with_limit(input_dict: dict, limit_key: str, limit_val: int) -> dict:
    """Devuelve copia del input con el límite sobreescrito."""
    out = copy.deepcopy(input_dict)
    out[limit_key] = limit_val
    return out


def run_safe(label: str, fn):
    print(f"\n── {label} ──")
    try:
        result = fn()
        print(f"  ✓ {label} OK")
        return result
    except Exception as exc:
        log.error("actor_failed", extra={"label": label, "err": str(exc)})
        print(f"  ✗ {label} FALLÓ: {exc}")
        return None


def main() -> int:
    cfg = load_client(CLIENT_ID)["platforms"]
    sb = Supabase()
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))
    start, end = ventana_ene_may()

    print(f"═══════════════════════════════════════════════════════")
    print(f"  DIAGNÓSTICO AMPLIADO — Ene 1 a May 31, 2026")
    print(f"  resultsLimit por actor: {RESULTS_LIMIT}")
    print(f"  Periodo en Supabase: '{PERIOD_ID}' (NO sobreescribe 'diagnostico')")
    print(f"═══════════════════════════════════════════════════════")

    # Asegurar que el periodo existe en tabla `periods`
    try:
        sb.upsert("periods", [{
            "id": PERIOD_ID,
            "client_id": CLIENT_ID,
            "label": "Diagnóstico ampliado (Ene-May 2026)",
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
        }], on_conflict="id")
        print("  ✓ Periodo registrado en tabla periods")
    except Exception as exc:
        log.warning("periods_upsert_failed", extra={"err": str(exc)})

    # Limpieza idempotente del periodo extendido
    print("\n→ Limpiando registros previos del periodo extendido…")
    for table in ("accounts", "aggregates"):
        try:
            sb.delete(table, f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}")
        except Exception as exc:
            log.warning("delete_failed", extra={"table": table, "err": str(exc)})

    platforms_data: dict[str, dict] = {}

    # ── Instagram ──
    ig_input = with_limit(cfg["instagram"]["apify"]["input"], "resultsLimit", RESULTS_LIMIT)
    ig_raw = run_safe(f"Instagram (apify/instagram-scraper, limit={RESULTS_LIMIT})", lambda:
        apify.run_actor_sync(cfg["instagram"]["apify"]["actor_id"], ig_input,
                              max_total_charge_usd=CAPS["instagram"]))
    if ig_raw:
        norm = normalize.normalize_instagram(ig_raw)
        all_posts = norm["posts"]
        norm["posts"] = _filter_window(all_posts, start, end)
        platforms_data["instagram"] = norm
        print(f"  Posts totales del actor: {len(all_posts)}")
        print(f"  Posts en ventana Ene-May: {len(norm['posts'])}")
        print(f"  Distribución por mes: {months_distribution(norm['posts'])}")

    # ── Facebook ──
    fb_account = None
    fb_posts: list[dict] = []
    fb_page_raw = run_safe("Facebook page (apify/facebook-pages-scraper)", lambda:
        apify.run_actor_sync(cfg["facebook"]["apify"]["page"]["actor_id"],
                              cfg["facebook"]["apify"]["page"]["input"],
                              max_total_charge_usd=CAPS["facebook_page"]))
    if fb_page_raw:
        fb_account = normalize.normalize_facebook_page(fb_page_raw)

    fb_posts_input = with_limit(cfg["facebook"]["apify"]["posts"]["input"], "resultsLimit", RESULTS_LIMIT)
    fb_posts_raw = run_safe(f"Facebook posts (limit={RESULTS_LIMIT})", lambda:
        apify.run_actor_sync(cfg["facebook"]["apify"]["posts"]["actor_id"], fb_posts_input,
                              max_total_charge_usd=CAPS["facebook_posts"]))
    if fb_posts_raw:
        all_fb = normalize.normalize_facebook_posts(fb_posts_raw)
        fb_posts = _filter_window(all_fb, start, end)
        print(f"  Posts totales del actor: {len(all_fb)}")
        print(f"  Posts en ventana Ene-May: {len(fb_posts)}")
        print(f"  Distribución por mes: {months_distribution(fb_posts)}")

    if fb_account or fb_posts:
        platforms_data["facebook"] = {"account": fb_account, "posts": fb_posts}

    # ── TikTok ──
    tt_account = None
    tt_prof_raw = run_safe("TikTok profile", lambda:
        apify.run_actor_sync(cfg["tiktok"]["apify"]["profile"]["actor_id"],
                              cfg["tiktok"]["apify"]["profile"]["input"],
                              max_total_charge_usd=CAPS["tiktok_profile"]))
    if tt_prof_raw:
        tt_prof_norm = normalize.normalize_tiktok(tt_prof_raw)
        tt_account = tt_prof_norm.get("account")

    tt_posts_input = with_limit(cfg["tiktok"]["apify"]["posts"]["input"], "resultsPerPage", RESULTS_LIMIT)
    tt_posts_raw = run_safe(f"TikTok posts (limit={RESULTS_LIMIT})", lambda:
        apify.run_actor_sync(cfg["tiktok"]["apify"]["posts"]["actor_id"], tt_posts_input,
                              max_total_charge_usd=CAPS["tiktok_posts"]))
    if tt_posts_raw:
        tt_norm = normalize.normalize_tiktok(tt_posts_raw)
        all_tt = tt_norm["posts"]
        tt_norm["posts"] = _filter_window(all_tt, start, end)
        if tt_account:
            tt_norm["account"] = tt_account
        platforms_data["tiktok"] = tt_norm
        print(f"  Posts totales del actor: {len(all_tt)}")
        print(f"  Posts en ventana Ene-May: {len(tt_norm['posts'])}")
        print(f"  Distribución por mes: {months_distribution(tt_norm['posts'])}")

    # ── LinkedIn ──
    li_input = with_limit(cfg["linkedin"]["apify"]["input"], "maxPosts", RESULTS_LIMIT)
    li_raw = run_safe(f"LinkedIn (harvestapi, maxPosts={RESULTS_LIMIT})", lambda:
        apify.run_actor_sync(cfg["linkedin"]["apify"]["actor_id"], li_input,
                              max_total_charge_usd=CAPS["linkedin"]))
    if li_raw:
        li_norm = normalize.normalize_linkedin(li_raw)
        all_li = li_norm["posts"]
        li_norm["posts"] = _filter_window(all_li, start, end)
        platforms_data["linkedin"] = li_norm
        print(f"  Posts totales del actor: {len(all_li)}")
        print(f"  Posts en ventana Ene-May: {len(li_norm['posts'])}")
        print(f"  Distribución por mes: {months_distribution(li_norm['posts'])}")

    # ── Persistir en Supabase ──
    print(f"\n═══════════════════════════════════════════════════════")
    print(f"  PERSISTIENDO A SUPABASE (period_id='{PERIOD_ID}')")
    print(f"═══════════════════════════════════════════════════════")

    for platform, block in platforms_data.items():
        if block.get("account"):
            sb.upsert("accounts", [_account_row(block["account"], PERIOD_ID, platform)],
                      on_conflict="client_id,period_id,platform")
            print(f"  ✓ {platform}: account upserted")
        posts = block.get("posts") or []
        if posts:
            sb.upsert("posts", _post_rows(CLIENT_ID, platform, posts), on_conflict="id")
            aggs = _platform_aggregates(posts)
            sb.upsert("aggregates", _aggregate_rows(PERIOD_ID, platform, aggs),
                      on_conflict="client_id,period_id,platform,metric_name")
            print(f"  ✓ {platform}: {len(posts)} posts + {len(aggs)} aggregates")

    # ── Reporte final ──
    print(f"\n═══════════════════════════════════════════════════════")
    print(f"  RESUMEN FINAL — ¿hasta dónde llegamos?")
    print(f"═══════════════════════════════════════════════════════")
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = platforms_data.get(plat) or {}
        posts = block.get("posts") or []
        print(f"\n  {plat.upper()}")
        print(f"    Total en ventana Ene-May: {len(posts)} posts")
        print(f"    Por mes: {months_distribution(posts)}")

    print(f"\n✅ Diagnóstico ampliado terminado.")
    print(f"   Periodo en Supabase: '{PERIOD_ID}'")
    print(f"   Siguiente paso: revisar logs para ver hasta qué mes llegamos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
