#!/usr/bin/env python3
"""Load-only: lee los datasets de Apify ya pagados (gratis) del ultimo intento
de junio y los persiste a Supabase. Tambien descarga thumbnails al instante
mientras las URLs CDN siguen frescas (estan a minutos del scrape).

Costo: $0 USD (solo lecturas + downloads).

NOTA: TikTok posts queda excluido porque el actor fallo con 400 — su dataset
quedo vacio. El resto (IG, FB pages, FB posts, TT profile, LinkedIn) si tienen
datasets disponibles.
"""
from __future__ import annotations

import hashlib
import io
import sys
import urllib.error
import urllib.request
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

try:
    from PIL import Image
except ImportError:
    print("✗ Pillow no instalado")
    sys.exit(1)

log = get_logger("load-junio")
CLIENT_ID = "comapan"
PERIOD_ID = "2026-06"
ROOT = Path(__file__).resolve().parent.parent
THUMBS_DIR = ROOT / "assets" / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)


def june_window():
    return (datetime(2026, 6, 1,  tzinfo=timezone.utc),
            datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc))


def latest_dataset(apify, actor_id: str, label: str):
    print(f"\n→ Buscando dataset reciente de {label}…")
    run = apify.last_succeeded_run_for_actor(actor_id)
    if not run:
        print(f"  ✗ Sin runs exitosos para {label}")
        return None
    ds = run.get("defaultDatasetId")
    print(f"  ✓ Dataset {ds} (finalizado {run.get('finishedAt', '?')})")
    return ds


def dl_thumb(url, plat, post_id):
    if not url: return None
    h = hashlib.sha1(str(post_id).encode()).hexdigest()[:12]
    fname = f"{plat}-{h}.jpg"
    dest = THUMBS_DIR / fname
    if dest.exists():
        return f"/assets/thumbs/{fname}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; DataliticaBot/1.0)",
            "Referer": "https://www.google.com/",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            data = r.read()
        if len(data) < 200: return None
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        if img.width > 400:
            r2 = 400 / img.width
            img = img.resize((400, int(img.height * r2)), Image.LANCZOS)
        img.save(dest, "JPEG", quality=60, optimize=True)
        return f"/assets/thumbs/{fname}"
    except Exception:
        return None


def main():
    cfg = load_client(CLIENT_ID)["platforms"]
    sb = Supabase()
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))
    start, end = june_window()

    print("═" * 60)
    print(f"  LOAD-ONLY JUNIO 2026 — datasets ya pagados ($0)")
    print(f"  Periodo: '{PERIOD_ID}'")
    print("═" * 60)

    # Limpieza idempotente de junio (por si hubo data parcial)
    print("\n→ Limpiando registros previos del periodo 2026-06…")
    for table in ("accounts", "aggregates"):
        try:
            sb.delete(table, f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}")
        except Exception as exc:
            log.warning("delete_failed", extra={"table": table, "err": str(exc)})

    platforms_data = {}

    # ── Instagram ──
    ig_ds = latest_dataset(apify, cfg["instagram"]["apify"]["actor_id"], "Instagram")
    if ig_ds:
        items = apify.dataset_items(ig_ds)
        norm = normalize.normalize_instagram(items)
        all_posts = norm["posts"]
        norm["posts"] = _filter_window(all_posts, start, end)
        platforms_data["instagram"] = norm
        print(f"  Total: {len(all_posts)}  Junio: {len(norm['posts'])}")

    # ── Facebook page ──
    fb_page_ds = latest_dataset(apify, cfg["facebook"]["apify"]["page"]["actor_id"], "FB page")
    fb_account = None
    if fb_page_ds:
        page_items = apify.dataset_items(fb_page_ds)
        fb_account = normalize.normalize_facebook_page(page_items)

    # ── Facebook posts ──
    fb_posts_ds = latest_dataset(apify, cfg["facebook"]["apify"]["posts"]["actor_id"], "FB posts")
    fb_posts = []
    if fb_posts_ds:
        post_items = apify.dataset_items(fb_posts_ds)
        all_fb = normalize.normalize_facebook_posts(post_items)
        fb_posts = _filter_window(all_fb, start, end)
        print(f"  Total: {len(all_fb)}  Junio: {len(fb_posts)}")

    if fb_account or fb_posts:
        platforms_data["facebook"] = {"account": fb_account, "posts": fb_posts}

    # ── TikTok profile (sin posts: ese actor fallo) ──
    tt_prof_ds = latest_dataset(apify, cfg["tiktok"]["apify"]["profile"]["actor_id"], "TT profile")
    if tt_prof_ds:
        prof_items = apify.dataset_items(tt_prof_ds)
        tt_norm = normalize.normalize_tiktok(prof_items)
        # Sin posts pero con cuenta
        if tt_norm.get("account"):
            platforms_data["tiktok"] = {"account": tt_norm["account"], "posts": []}
            print("  Solo cuenta (posts del actor fallaron con HTTP 400)")

    # ── LinkedIn ──
    li_ds = latest_dataset(apify, cfg["linkedin"]["apify"]["actor_id"], "LinkedIn")
    if li_ds:
        li_items = apify.dataset_items(li_ds)
        li_norm = normalize.normalize_linkedin(li_items)
        all_li = li_norm["posts"]
        li_norm["posts"] = _filter_window(all_li, start, end)
        platforms_data["linkedin"] = li_norm
        print(f"  Total: {len(all_li)}  Junio: {len(li_norm['posts'])}")

    # ── Persistir a Supabase + descargar thumbnails ──
    print(f"\n{'═' * 60}")
    print(f"  PERSISTIENDO A SUPABASE + DESCARGANDO THUMBS")
    print(f"{'═' * 60}")

    now_iso = datetime.now(timezone.utc).isoformat()

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

            # Descargar thumbnails al instante
            dl_ok = 0; dl_fail = 0
            for p in posts:
                local = dl_thumb(p.get("media_url"), platform, p.get("id"))
                if local:
                    try:
                        sb.update("posts", f"id=eq.{p['id']}", {
                            "media_url_local":         local,
                            "thumbnail_downloaded_at": now_iso,
                        })
                        dl_ok += 1
                    except Exception:
                        dl_fail += 1
                else:
                    dl_fail += 1
            print(f"    └ thumbnails: ✓{dl_ok}  ✗{dl_fail}")

    print(f"\n✅ Load-only terminado.")
    print(f"   Siguiente paso: build_diagnostico_extendido con period=2026-06")
    return 0


if __name__ == "__main__":
    sys.exit(main())
