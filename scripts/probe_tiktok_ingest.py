#!/usr/bin/env python3
"""Diagnostico: compara lo que TikTok Apify entrego vs lo que quedo en Supabase.
Costo: $0 (solo lectura via API).
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TOKEN = os.environ.get("APIFY_TOKEN")
if not TOKEN:
    print("✗ APIFY_TOKEN ausente")
    sys.exit(1)

TT_POSTS_ACTOR = "GdWCkxBtKWOsKjdch"  # clockworks/tiktok-scraper


def get_recent_runs(actor_id, limit=5):
    url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={TOKEN}&desc=1&limit={limit}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())["data"]["items"]


def get_dataset_items(dataset_id, limit=100):
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={TOKEN}&format=json&limit={limit}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def main():
    print("═" * 60)
    print("  PROBE: TikTok posts actor — últimos runs")
    print("═" * 60)

    runs = get_recent_runs(TT_POSTS_ACTOR, limit=5)
    print(f"\nÚltimos {len(runs)} runs:")
    for r in runs:
        print(f"  {r.get('startedAt', '?')[:19]}  status={r.get('status')}  items_out={r.get('stats',{}).get('outputBodyBytes','?')}  ds={r.get('defaultDatasetId')}")

    # Último run exitoso
    last_ok = next((r for r in runs if r.get("status") == "SUCCEEDED"), None)
    if not last_ok:
        print("\n✗ Sin runs exitosos recientes")
        return 1

    ds_id = last_ok["defaultDatasetId"]
    print(f"\n→ Leyendo dataset del último run OK ({ds_id})…")
    items = get_dataset_items(ds_id)
    print(f"  {len(items)} items en el dataset")

    # Ver fechas de los primeros items para saber si fueron de julio
    print(f"\n  Items (primeros 10):")
    for i, it in enumerate(items[:10]):
        # Diferentes campos posibles de fecha en TikTok
        posted = it.get("createTimeISO") or it.get("createTime") or "?"
        author = (it.get("authorMeta") or {}).get("name") or "?"
        text = (it.get("text") or "")[:60]
        print(f"    [{i}] @{author}  posted={posted}  {text}")

    # Filtrar a julio 2026 (Bogotá UTC-5)
    BG = timezone(timedelta(hours=-5))
    START = datetime(2026, 7, 1, tzinfo=BG)
    END = datetime(2026, 7, 31, 23, 59, 59, tzinfo=BG)

    def to_dt(s):
        if not s: return None
        try:
            if isinstance(s, int):
                return datetime.fromtimestamp(s, tz=timezone.utc).astimezone(BG)
            t = datetime.fromisoformat(s.replace("Z", "+00:00")) if str(s).endswith("Z") else datetime.fromisoformat(str(s))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return t.astimezone(BG)
        except Exception:
            return None

    en_julio = 0
    for it in items:
        posted = it.get("createTimeISO") or it.get("createTime")
        dt = to_dt(posted)
        if dt and START <= dt <= END:
            en_julio += 1
    print(f"\n  De los {len(items)} items, {en_julio} caen en ventana julio 2026 (Bogotá)")

    print("\n" + "═" * 60)
    if en_julio == 0:
        print("  DIAGNÓSTICO: el actor de TikTok NO trajo posts de julio.")
        print("  Razones posibles:")
        print("  - El scrape no captó los posts recientes (podría ser latencia de indexación)")
        print("  - Los posts existen en TikTok pero el actor no los ve (rate limit, cache)")
        print("  - Necesita re-ingestar solo TT")
    else:
        print(f"  DIAGNÓSTICO: el actor SÍ trajo {en_julio} posts de julio.")
        print("  Si Supabase tiene 0, hay un bug en el filtro o en el upsert.")
    print("═" * 60)


if __name__ == "__main__":
    main()
