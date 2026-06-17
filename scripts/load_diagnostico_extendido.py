#!/usr/bin/env python3
"""LOAD-ONLY: lee los datasets de Apify YA EJECUTADOS (gratis) y persiste
a Supabase con period_id='diagnostico-extendido'.

Costo: $0 USD. Reusa el output del workflow `ingest_diagnostico_ampliado.yml`
que ya se corrió a las ~20:50 UTC del 17-jun-2026.

Para cada actor:
  1. Busca la última corrida exitosa (last_succeeded_run_for_actor)
  2. Lee sus items del dataset (gratis)
  3. Normaliza, filtra a Ene 1 - May 31, persiste a Supabase
"""
from __future__ import annotations

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

log = get_logger("load-diag-ext")
CLIENT_ID = "comapan"
PERIOD_ID = "diagnostico-extendido"


def ventana_ene_may() -> tuple[datetime, datetime]:
    return (datetime(2026, 1, 1,  tzinfo=timezone.utc),
            datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc))


def months_distribution(posts: list[dict]) -> str:
    by_month: dict[str, int] = {}
    for p in posts:
        ts = p.get("timestamp")
        if isinstance(ts, datetime):
            key = f"{ts.year}-{ts.month:02d}"
            by_month[key] = by_month.get(key, 0) + 1
    if not by_month:
        return "(sin posts)"
    return " · ".join(f"{m}: {n}" for m, n in sorted(by_month.items()))


def latest_dataset_id(apify: ApifyClient, actor_id: str, label: str) -> str | None:
    """Trae el dataset_id del último run exitoso. Lectura = gratis."""
    print(f"\n→ Buscando última corrida exitosa de {label}…")
    run = apify.last_succeeded_run_for_actor(actor_id)
    if not run:
        print(f"  ✗ No hay corridas exitosas para {label}")
        return None
    ds_id = run.get("defaultDatasetId")
    finished = run.get("finishedAt", "?")
    print(f"  ✓ Dataset {ds_id} (finalizado {finished})")
    return ds_id


def main() -> int:
    cfg = load_client(CLIENT_ID)["platforms"]
    sb = Supabase()
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))
    start, end = ventana_ene_may()

    print(f"═══════════════════════════════════════════════════════")
    print(f"  LOAD-ONLY DIAGNÓSTICO AMPLIADO (Ene-May 2026)")
    print(f"  Costo: $0 USD (solo lecturas de datasets ya pagados)")
    print(f"  Periodo Supabase: '{PERIOD_ID}'")
    print(f"═══════════════════════════════════════════════════════")

    # Limpiar previo del periodo extendido (idempotente)
    print("\n→ Limpiando registros previos del periodo extendido…")
    for table in ("accounts", "aggregates"):
        try:
            sb.delete(table, f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}")
        except Exception as exc:
            log.warning("delete_failed", extra={"table": table, "err": str(exc)})

    platforms_data: dict[str, dict] = {}

    # ── Instagram ──
    ig_ds = latest_dataset_id(apify, cfg["instagram"]["apify"]["actor_id"], "Instagram")
    if ig_ds:
        items = apify.dataset_items(ig_ds)
        norm = normalize.normalize_instagram(items)
        all_posts = norm["posts"]
        norm["posts"] = _filter_window(all_posts, start, end)
        platforms_data["instagram"] = norm
        print(f"  Posts brutos: {len(all_posts)}")
        print(f"  Posts Ene-May: {len(norm['posts'])}")
        print(f"  Por mes: {months_distribution(norm['posts'])}")

    # ── Facebook page ──
    fb_page_ds = latest_dataset_id(apify, cfg["facebook"]["apify"]["page"]["actor_id"], "FB page")
    fb_account = None
    if fb_page_ds:
        page_items = apify.dataset_items(fb_page_ds)
        fb_account = normalize.normalize_facebook_page(page_items)
        print(f"  Items: {len(page_items)} (esperado: 1 fila perfil)")

    # ── Facebook posts ──
    fb_posts_ds = latest_dataset_id(apify, cfg["facebook"]["apify"]["posts"]["actor_id"], "FB posts")
    fb_posts: list[dict] = []
    if fb_posts_ds:
        post_items = apify.dataset_items(fb_posts_ds)
        all_fb = normalize.normalize_facebook_posts(post_items)
        fb_posts = _filter_window(all_fb, start, end)
        print(f"  Posts brutos: {len(all_fb)}")
        print(f"  Posts Ene-May: {len(fb_posts)}")
        print(f"  Por mes: {months_distribution(fb_posts)}")

    if fb_account or fb_posts:
        platforms_data["facebook"] = {"account": fb_account, "posts": fb_posts}

    # ── TikTok profile ──
    tt_prof_ds = latest_dataset_id(apify, cfg["tiktok"]["apify"]["profile"]["actor_id"], "TT profile")
    tt_account = None
    if tt_prof_ds:
        prof_items = apify.dataset_items(tt_prof_ds)
        tt_prof_norm = normalize.normalize_tiktok(prof_items)
        tt_account = tt_prof_norm.get("account")

    # ── TikTok posts ──
    tt_posts_ds = latest_dataset_id(apify, cfg["tiktok"]["apify"]["posts"]["actor_id"], "TT posts")
    if tt_posts_ds:
        tt_items = apify.dataset_items(tt_posts_ds)
        tt_norm = normalize.normalize_tiktok(tt_items)
        all_tt = tt_norm["posts"]
        tt_norm["posts"] = _filter_window(all_tt, start, end)
        if tt_account:
            tt_norm["account"] = tt_account
        platforms_data["tiktok"] = tt_norm
        print(f"  Posts brutos: {len(all_tt)}")
        print(f"  Posts Ene-May: {len(tt_norm['posts'])}")
        print(f"  Por mes: {months_distribution(tt_norm['posts'])}")

    # ── LinkedIn ──
    li_ds = latest_dataset_id(apify, cfg["linkedin"]["apify"]["actor_id"], "LinkedIn")
    if li_ds:
        li_items = apify.dataset_items(li_ds)
        li_norm = normalize.normalize_linkedin(li_items)
        all_li = li_norm["posts"]
        li_norm["posts"] = _filter_window(all_li, start, end)
        platforms_data["linkedin"] = li_norm
        print(f"  Posts brutos: {len(all_li)}")
        print(f"  Posts Ene-May: {len(li_norm['posts'])}")
        print(f"  Por mes: {months_distribution(li_norm['posts'])}")

    # ── Persistir ──
    print(f"\n═══════════════════════════════════════════════════════")
    print(f"  PERSISTIENDO A SUPABASE")
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

    # Resumen
    print(f"\n═══════════════════════════════════════════════════════")
    print(f"  RESUMEN FINAL")
    print(f"═══════════════════════════════════════════════════════")
    total = 0
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = platforms_data.get(plat) or {}
        n = len(block.get("posts") or [])
        total += n
        print(f"  {plat:10s}  {n:3d} posts Ene-May")
    print(f"  {'TOTAL':10s}  {total:3d} posts")

    print(f"\n✅ Load-only terminado. Periodo: '{PERIOD_ID}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
