#!/usr/bin/env python3
"""Ingester FULL para junio 2026: lanza los 4 actores con caps de seguridad,
filtra a calendario junio (1-30), y persiste todo en Supabase.

Costo esperado: ~$0.80 USD. Cap total absoluto: ~$1.90 USD.

Caps por actor (max_total_charge_usd):
    Instagram:     $0.50
    Facebook page: $0.20
    Facebook posts:$0.40
    TikTok prof:   $0.20
    TikTok posts:  $0.30
    LinkedIn:      $0.50
    ─────────────────────
    TOTAL cap:     $2.10

Uso (en workflow):
    python scripts/ingest_junio_full.py
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

# Reusar helpers ya probados del script principal
from scripts.ingest_to_supabase import (
    _filter_window, _platform_aggregates,
    _account_row, _post_rows, _aggregate_rows,
)
import hashlib as _hashlib
import io as _io
import urllib.request as _urlreq
import urllib.error as _urlerr
from pathlib import Path as _Path
try:
    from PIL import Image as _Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# Carpeta para thumbnails locales (siempre se intentan bajar al ingest mientras URL viva)
_THUMBS = _Path(__file__).resolve().parent.parent / "assets" / "thumbs"
_THUMBS.mkdir(parents=True, exist_ok=True)


def _dl_thumb(url: str, plat: str, post_id: str) -> str | None:
    """Descarga, comprime y guarda thumbnail. Retorna path local o None."""
    if not url or not _PIL_OK:
        return None
    h = _hashlib.sha1(str(post_id).encode()).hexdigest()[:12]
    fname = f"{plat}-{h}.jpg"
    dest = _THUMBS / fname
    if dest.exists():
        return f"/assets/thumbs/{fname}"
    try:
        req = _urlreq.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; DataliticaBot/1.0)",
            "Referer": "https://www.google.com/",
        })
        with _urlreq.urlopen(req, timeout=8) as r:
            data = r.read()
        if len(data) < 200:
            return None
        img = _Image.open(_io.BytesIO(data))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        if img.width > 400:
            r2 = 400 / img.width
            img = img.resize((400, int(img.height * r2)), _Image.LANCZOS)
        img.save(dest, "JPEG", quality=60, optimize=True)
        return f"/assets/thumbs/{fname}"
    except Exception:
        return None

log = get_logger("ingest-junio-full")
CLIENT_ID = "comapan"
PERIOD_ID = "2026-06"

# Caps de seguridad por actor (en USD). Si Apify intenta cobrar más, devuelve error.
CAPS = {
    "instagram":      0.50,
    "facebook_page":  0.20,
    "facebook_posts": 0.40,
    "tiktok_profile": 0.20,
    "tiktok_posts":   0.30,
    "linkedin":       0.50,
}


def june_window() -> tuple[datetime, datetime]:
    return (datetime(2026, 6, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc))


def run_platform(name: str, label: str, fn) -> dict:
    """Wrapper: corre el actor y captura errores sin tumbar todo el script."""
    print(f"\n── {label} ──")
    try:
        result = fn()
        print(f"  ✓ {label} OK")
        return {"ok": True, "data": result}
    except Exception as exc:
        log.error(f"{name}_failed", extra={"err": str(exc)})
        print(f"  ✗ {label} FALLÓ: {exc}")
        return {"ok": False, "err": str(exc)}


def main() -> int:
    cfg = load_client(CLIENT_ID)["platforms"]
    sb = Supabase()
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))
    start, end = june_window()

    print(f"═══════════════════════════════════════════════")
    print(f"  INGESTA FULL — junio 2026 ({start.date()} a {end.date()})")
    print(f"═══════════════════════════════════════════════")

    # Idempotencia: borrar lo viejo de junio antes
    print("\n→ Limpiando registros previos de 2026-06…")
    for table in ("accounts", "aggregates", "posts"):
        try:
            sb.delete(table, f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}")
        except Exception as exc:
            log.warning("delete_failed", extra={"table": table, "err": str(exc)})

    platforms_data: dict[str, dict] = {}

    # ── Instagram ──
    ig_run = run_platform("instagram", "Instagram (apify/instagram-scraper)", lambda:
        normalize.normalize_instagram(
            apify.run_actor_sync(
                cfg["instagram"]["apify"]["actor_id"],
                cfg["instagram"]["apify"]["input"],
                max_total_charge_usd=CAPS["instagram"],
            )
        )
    )
    if ig_run["ok"]:
        ig_run["data"]["posts"] = _filter_window(ig_run["data"]["posts"], start, end)
        platforms_data["instagram"] = ig_run["data"]
        print(f"  Posts en junio: {len(ig_run['data']['posts'])}")

    # ── Facebook ── (2 actores: pages + posts)
    fb_account = None
    fb_posts = []
    fb_page_run = run_platform("fb_page", "Facebook page (apify/facebook-pages-scraper)", lambda:
        normalize.normalize_facebook_page(
            apify.run_actor_sync(
                cfg["facebook"]["apify"]["page"]["actor_id"],
                cfg["facebook"]["apify"]["page"]["input"],
                max_total_charge_usd=CAPS["facebook_page"],
            )
        )
    )
    if fb_page_run["ok"]:
        fb_account = fb_page_run["data"]

    fb_posts_run = run_platform("fb_posts", "Facebook posts (apify/facebook-posts-scraper)", lambda:
        _filter_window(
            normalize.normalize_facebook_posts(
                apify.run_actor_sync(
                    cfg["facebook"]["apify"]["posts"]["actor_id"],
                    cfg["facebook"]["apify"]["posts"]["input"],
                    max_total_charge_usd=CAPS["facebook_posts"],
                )
            ),
            start, end
        )
    )
    if fb_posts_run["ok"]:
        fb_posts = fb_posts_run["data"]
        print(f"  Posts en junio: {len(fb_posts)}")

    if fb_account or fb_posts:
        platforms_data["facebook"] = {"account": fb_account, "posts": fb_posts}

    # ── TikTok ── (2 actores: profile + posts)
    tt_profile = None
    tt_posts_data = None
    tt_prof_run = run_platform("tt_profile", "TikTok profile (clockworks/tiktok-profile-scraper)", lambda:
        normalize.normalize_tiktok(
            apify.run_actor_sync(
                cfg["tiktok"]["apify"]["profile"]["actor_id"],
                cfg["tiktok"]["apify"]["profile"]["input"],
                max_total_charge_usd=CAPS["tiktok_profile"],
            )
        )
    )
    if tt_prof_run["ok"]:
        tt_profile = tt_prof_run["data"].get("account")

    tt_posts_run = run_platform("tt_posts", "TikTok posts (clockworks/tiktok-scraper)", lambda:
        normalize.normalize_tiktok(
            apify.run_actor_sync(
                cfg["tiktok"]["apify"]["posts"]["actor_id"],
                cfg["tiktok"]["apify"]["posts"]["input"],
                max_total_charge_usd=CAPS["tiktok_posts"],
            )
        )
    )
    if tt_posts_run["ok"]:
        tt_posts_data = tt_posts_run["data"]
        tt_posts_data["posts"] = _filter_window(tt_posts_data["posts"], start, end)
        if tt_profile:
            tt_posts_data["account"] = tt_profile  # priorizar perfil completo
        platforms_data["tiktok"] = tt_posts_data
        print(f"  Posts en junio: {len(tt_posts_data['posts'])}")

    # ── LinkedIn ──
    li_run = run_platform("linkedin", "LinkedIn (harvestapi/linkedin-company-posts)", lambda:
        normalize.normalize_linkedin(
            apify.run_actor_sync(
                cfg["linkedin"]["apify"]["actor_id"],
                cfg["linkedin"]["apify"]["input"],
                max_total_charge_usd=CAPS["linkedin"],
            )
        )
    )
    if li_run["ok"]:
        li_run["data"]["posts"] = _filter_window(li_run["data"]["posts"], start, end)
        platforms_data["linkedin"] = li_run["data"]
        print(f"  Posts en junio: {len(li_run['data']['posts'])}")

    # ── Persistir a Supabase ──
    print(f"\n═══════════════════════════════════════════════")
    print(f"  PERSISTIENDO A SUPABASE")
    print(f"═══════════════════════════════════════════════")

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

            # Descargar thumbnails INMEDIATAMENTE (URLs CDN expiran en horas)
            from datetime import datetime as _dtnow, timezone as _tznow
            now_iso_dl = _dtnow.now(_tznow.utc).isoformat()
            dl_ok = 0; dl_fail = 0
            for p in posts:
                local = _dl_thumb(p.get("media_url"), platform, p.get("id"))
                if local:
                    try:
                        sb.update("posts", f"id=eq.{p['id']}", {
                            "media_url_local":         local,
                            "thumbnail_downloaded_at": now_iso_dl,
                        })
                        dl_ok += 1
                    except Exception:
                        dl_fail += 1
                else:
                    dl_fail += 1
            print(f"    └ thumbnails: ✓{dl_ok}  ✗{dl_fail}")
        else:
            print(f"  ⚠ {platform}: sin posts en junio (cuenta sí guardada si existe)")

    print(f"\n═══════════════════════════════════════════════")
    print(f"  RESUMEN")
    print(f"═══════════════════════════════════════════════")
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = platforms_data.get(plat) or {}
        n = len(block.get("posts") or [])
        ok = "✓" if plat in platforms_data else "✗"
        print(f"  {ok} {plat:10s} {n:3d} posts en ventana")

    print(f"\n✅ Ingesta junio terminada.")
    print(f"   Siguiente paso: workflow 'Generate Narratives' con period=2026-06")
    return 0


if __name__ == "__main__":
    sys.exit(main())
