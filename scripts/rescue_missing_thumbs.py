#!/usr/bin/env python3
"""Rescue: descargar los thumbnails de posts que tienen media_url_local
pero cuyo archivo NO existe en disco. Usa la CDN URL original (media_url).

Idempotente. Silencioso para los que ya existen. Solo intenta downloads
para archivos faltantes.
"""
from __future__ import annotations
import hashlib
import io
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.load.supabase_client import Supabase
from pipeline.util.log import get_logger

try:
    from PIL import Image
except ImportError:
    print("✗ Pillow no instalado")
    sys.exit(1)

log = get_logger("rescue-missing-thumbs")
CLIENT_ID = "comapan"
ROOT = Path(__file__).resolve().parent.parent
THUMBS_DIR = ROOT / "assets" / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)


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
        if img.width > 400:
            r2 = 400 / img.width
            img = img.resize((400, int(img.height * r2)), Image.LANCZOS)
        img.save(dest, "JPEG", quality=60, optimize=True)
        return True
    except Exception:
        return False


def main() -> int:
    sb = Supabase()
    print("→ Leyendo posts con media_url_local pero archivo ausente…")
    posts = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")

    to_rescue = []
    for p in posts:
        local = p.get("media_url_local")
        if not local or not local.startswith("/assets/thumbs/"):
            continue
        # Path absoluto en disco
        fname = local.replace("/assets/thumbs/", "")
        dest = THUMBS_DIR / fname
        if dest.exists():
            continue
        # Falta el archivo, intentar rescatar con la CDN URL original
        cdn = p.get("media_url")
        if not cdn or not cdn.startswith("http"):
            continue
        to_rescue.append((p.get("id"), p.get("platform"), cdn, dest, fname))

    print(f"  Posts para rescatar: {len(to_rescue)}")
    if not to_rescue:
        print("✅ Nada que rescatar.")
        return 0

    ok = 0; fail = 0
    for pid, plat, cdn, dest, fname in to_rescue:
        if download_and_save(cdn, dest):
            ok += 1
            if ok <= 5 or ok % 20 == 0:
                sz = dest.stat().st_size // 1024
                print(f"    ✓ [{ok}] {fname} ({sz}KB)")
        else:
            fail += 1

    print(f"\n══ Rescate: ✓{ok}  ✗{fail} (URLs CDN vencidas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
