#!/usr/bin/env python3
"""Rescue thumbnails: re-scrape Apify + descarga inmediata mientras URLs estan vivas.

Soluciona el problema de CDN URLs expiradas que dejaron 275/298 posts sin
imagen. Las URLs duran 1-3 horas tras el scrape — descargamos al instante.

ESTRATEGIA:
  1. Re-correr los 4 actores Apify con resultsLimit=300 (para cubrir Ene-May)
  2. Por cada post devuelto: matching por post.id contra Supabase
  3. Si el post existe y NO tiene media_url_local: descargar AHORA, comprimir,
     guardar en /assets/thumbs/, PATCH Supabase con media_url_local

COSTOS CAP (max_total_charge_usd):
  IG:               $1.00
  FB page:          $0.20
  FB posts:         $0.60
  TT profile:       $0.20
  TT posts:         $0.50
  LinkedIn:         $0.90
  ─────────────────────────
  TOTAL CAP:        $3.40

Idempotente: skip de posts que ya tienen media_url_local.
"""
from __future__ import annotations

import copy
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

try:
    from PIL import Image
except ImportError:
    print("✗ Pillow no instalado")
    sys.exit(1)

log = get_logger("rescue-thumbs")
CLIENT_ID = "comapan"
ROOT = Path(__file__).resolve().parent.parent
THUMBS_DIR = ROOT / "assets" / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

MAX_WIDTH = 400
JPEG_QUALITY = 60
RESULTS_LIMIT = 300

CAPS = {
    "instagram":      1.00,
    "facebook_page":  0.20,
    "facebook_posts": 0.60,
    "tiktok_profile": 0.20,
    "tiktok_posts":   0.50,
    "linkedin":       0.90,
}


def safe_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def download_and_save(url: str, dest: Path, timeout: int = 8) -> bool:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; DataliticaBot/1.0)",
            "Referer": "https://www.google.com/",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if len(data) < 200:
            return False
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            new_h = int(img.height * ratio)
            img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)
        img.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return True
    except Exception:
        return False


def with_limit(input_dict: dict, key: str, val: int) -> dict:
    out = copy.deepcopy(input_dict)
    out[key] = val
    return out


def rescue_platform(plat: str, normalized_posts: list[dict], sb: Supabase) -> tuple[int, int]:
    """Para cada post normalizado, descarga su media_url e update Supabase. Retorna (ok, fail)."""
    if not normalized_posts:
        return 0, 0
    # Pull state actual de la tabla
    rows = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}&platform=eq.{plat}")
    by_id = {str(r["id"]): r for r in rows}
    print(f"  Posts en Supabase ({plat}): {len(by_id)}")

    ok = 0; fail = 0; skip = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for post in normalized_posts:
        pid = str(post.get("id") or "")
        media_url = post.get("media_url") or ""
        if not pid or not media_url:
            continue
        existing = by_id.get(pid)
        if not existing:
            # Post nuevo (no estaba en Supabase) — skip, lo manejara el ingest normal
            continue
        if existing.get("media_url_local"):
            skip += 1
            continue

        h = safe_hash(pid)
        fname = f"{plat}-{h}.jpg"
        dest = THUMBS_DIR / fname

        if dest.exists() or download_and_save(media_url, dest):
            try:
                sb.update("posts", f"id=eq.{pid}", {
                    "media_url_local":         f"/assets/thumbs/{fname}",
                    "thumbnail_downloaded_at": now_iso,
                })
                ok += 1
                if ok <= 5 or ok % 25 == 0:
                    sz = dest.stat().st_size // 1024 if dest.exists() else "?"
                    print(f"    ✓ [{ok}] {fname} ({sz}KB)")
            except Exception as e:
                print(f"    ⚠ Update Supabase fallo para {pid}: {e}")
                fail += 1
        else:
            fail += 1
            if fail <= 3:
                print(f"    ✗ download fallo {plat} {pid[:20]}")
    print(f"  {plat}: ✓{ok}  ✗{fail}  skip(ya tenian){skip}")
    return ok, fail


def main() -> int:
    cfg = load_client(CLIENT_ID)["platforms"]
    sb = Supabase()
    apify = ApifyClient(token=require_env("APIFY_TOKEN"))

    print("═" * 60)
    print("  RESCUE THUMBNAILS — re-scrape + descarga al instante")
    print(f"  resultsLimit: {RESULTS_LIMIT} | cap total: ~$3.40 USD")
    print("═" * 60)

    total_ok = 0; total_fail = 0

    # IG
    print("\n── Instagram ──")
    try:
        ig_input = with_limit(cfg["instagram"]["apify"]["input"], "resultsLimit", RESULTS_LIMIT)
        ig_items = apify.run_actor_sync(cfg["instagram"]["apify"]["actor_id"], ig_input,
                                         max_total_charge_usd=CAPS["instagram"])
        print(f"  Actor retorno {len(ig_items)} items")
        norm = normalize.normalize_instagram(ig_items)
        ok, fail = rescue_platform("instagram", norm["posts"], sb)
        total_ok += ok; total_fail += fail
    except Exception as e:
        print(f"  ✗ IG fallo: {e}")

    # FB posts (no necesitamos page actor para thumbnails)
    print("\n── Facebook posts ──")
    try:
        fb_input = with_limit(cfg["facebook"]["apify"]["posts"]["input"], "resultsLimit", RESULTS_LIMIT)
        fb_items = apify.run_actor_sync(cfg["facebook"]["apify"]["posts"]["actor_id"], fb_input,
                                         max_total_charge_usd=CAPS["facebook_posts"])
        print(f"  Actor retorno {len(fb_items)} items")
        fb_posts = normalize.normalize_facebook_posts(fb_items)
        ok, fail = rescue_platform("facebook", fb_posts, sb)
        total_ok += ok; total_fail += fail
    except Exception as e:
        print(f"  ✗ FB fallo: {e}")

    # TT posts
    print("\n── TikTok posts ──")
    try:
        tt_input = with_limit(cfg["tiktok"]["apify"]["posts"]["input"], "resultsPerPage", RESULTS_LIMIT)
        tt_items = apify.run_actor_sync(cfg["tiktok"]["apify"]["posts"]["actor_id"], tt_input,
                                         max_total_charge_usd=CAPS["tiktok_posts"])
        print(f"  Actor retorno {len(tt_items)} items")
        tt_norm = normalize.normalize_tiktok(tt_items)
        ok, fail = rescue_platform("tiktok", tt_norm["posts"], sb)
        total_ok += ok; total_fail += fail
    except Exception as e:
        print(f"  ✗ TT fallo: {e}")

    # LinkedIn
    print("\n── LinkedIn ──")
    try:
        li_input = with_limit(cfg["linkedin"]["apify"]["input"], "maxPosts", RESULTS_LIMIT)
        li_items = apify.run_actor_sync(cfg["linkedin"]["apify"]["actor_id"], li_input,
                                         max_total_charge_usd=CAPS["linkedin"])
        print(f"  Actor retorno {len(li_items)} items")
        li_norm = normalize.normalize_linkedin(li_items)
        ok, fail = rescue_platform("linkedin", li_norm["posts"], sb)
        total_ok += ok; total_fail += fail
    except Exception as e:
        print(f"  ✗ LI fallo: {e}")

    print(f"\n{'═' * 60}")
    print(f"  RESUMEN: rescatadas {total_ok}, fallidas {total_fail}")
    print(f"  Carpeta: {THUMBS_DIR.relative_to(ROOT)}")
    print(f"{'═' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
