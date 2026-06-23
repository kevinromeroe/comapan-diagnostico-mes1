#!/usr/bin/env python3
"""Descarga thumbnails de posts y los guarda comprimidos en /assets/thumbs/.

Soluciona el problema de URLs firmadas del CDN de IG/FB/TT/LI que expiran
en horas. Los thumbs locales viven con el repo y se sirven via GitHub Pages.

- Lee posts WHERE media_url_local IS NULL (idempotente)
- Descarga con timeout corto (8s)
- Comprime a 400px ancho, JPEG quality 60
- Guarda en /assets/thumbs/{platform}-{post_id_hash}.jpg
- Actualiza posts.media_url_local + thumbnail_downloaded_at
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

from pipeline.load.supabase_client import Supabase
from pipeline.util.log import get_logger

try:
    from PIL import Image
except ImportError:
    print("✗ Pillow no instalado. Agregar Pillow>=10.0 a requirements.txt")
    sys.exit(1)

log = get_logger("download-thumbs")
CLIENT_ID = "comapan"
ROOT = Path(__file__).resolve().parent.parent
THUMBS_DIR = ROOT / "assets" / "thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

MAX_WIDTH = 400
JPEG_QUALITY = 60


def safe_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def download_and_save(url: str, dest: Path, timeout: int = 8) -> bool:
    """Baja la imagen, la comprime y guarda. True si exito."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; DataliticaBot/1.0)",
            "Referer": "https://www.google.com/",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if len(data) < 200:  # imagen muy chica = probablemente placeholder
            return False
        img = Image.open(io.BytesIO(data))
        # Convertir a RGB si tiene alpha
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        # Redimensionar manteniendo aspect ratio
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            new_h = int(img.height * ratio)
            img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)
        # Guardar comprimido
        img.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        return False
    except Exception as e:
        log.warning("download_failed", extra={"url": url[:80], "err": str(e)})
        return False


def main() -> int:
    sb = Supabase()
    print("→ Leyendo posts sin media_url_local…")
    posts = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")
    pending = [p for p in posts if p.get("media_url") and not p.get("media_url_local")]
    print(f"  Total posts: {len(posts)}")
    print(f"  Sin thumbnail local: {len(pending)}")

    if not pending:
        print("✅ Todos los posts ya tienen thumbnail local. Nada que hacer.")
        return 0

    ok = 0
    fail = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    updates = []

    for i, p in enumerate(pending, 1):
        plat = p.get("platform", "x")
        pid = p.get("id") or ""
        media_url = p.get("media_url") or ""

        # Nombre de archivo determinista
        h = safe_hash(pid)
        fname = f"{plat}-{h}.jpg"
        dest = THUMBS_DIR / fname

        # Si ya existe en disco (corrida previa), solo registrar en Supabase
        if dest.exists():
            updates.append({"id": pid, "media_url_local": f"/assets/thumbs/{fname}",
                            "thumbnail_downloaded_at": now_iso})
            ok += 1
            continue

        success = download_and_save(media_url, dest)
        if success:
            updates.append({"id": pid, "media_url_local": f"/assets/thumbs/{fname}",
                            "thumbnail_downloaded_at": now_iso})
            ok += 1
            print(f"  [{i}/{len(pending)}] ✓ {fname} ({dest.stat().st_size // 1024}KB)")
        else:
            fail += 1
            if fail <= 5:
                print(f"  [{i}/{len(pending)}] ✗ {plat} {pid[:20]} (CDN expirada)")

    # PATCH una fila a la vez (mas seguro que upsert con NOT NULL constraints)
    if updates:
        print(f"\n→ Actualizando {len(updates)} filas en posts table (PATCH)…")
        for u in updates:
            try:
                sb.update("posts", f"id=eq.{u['id']}", {
                    "media_url_local":         u["media_url_local"],
                    "thumbnail_downloaded_at": u["thumbnail_downloaded_at"],
                })
            except Exception as e:
                print(f"  ⚠ Update falló id={u['id']}: {e}")
        print(f"  ✓ {len(updates)} filas actualizadas")

    print(f"\n══ RESUMEN ══")
    print(f"  Descargados: {ok}/{len(pending)}")
    print(f"  Fallaron:    {fail}/{len(pending)}")
    print(f"  Carpeta:     {THUMBS_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
