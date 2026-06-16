"""Descarga thumbnails de los top5 posts y los guarda con nombre estable.

Naming convention: assets/thumbs/<prefix>-<sha1[:10]>.jpg
   donde <prefix> es ig | fb | tt | li según la plataforma.

Reemplaza el `media_url` en cada top5 con el path local relativo.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from PIL import Image

from pipeline.util.config import PROJECT_ROOT
from pipeline.util.log import get_logger

log = get_logger(__name__)

THUMBS_DIR = PROJECT_ROOT / "assets" / "thumbs"

PLATFORM_PREFIX = {
    "instagram": "ig",
    "facebook": "fb",
    "tiktok": "tt",
    "linkedin": "li",
}


def download_thumb(url: str, post_id: str, platform: str, *, max_width: int = 720, quality: int = 85) -> str | None:
    """Descarga, redimensiona, guarda. Retorna el path relativo o None si falla."""
    if not url:
        return None
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    prefix = PLATFORM_PREFIX.get(platform, "xx")
    h = hashlib.sha1(post_id.encode()).hexdigest()[:10]
    fname = f"{prefix}-{h}.jpg"
    target = THUMBS_DIR / fname

    if target.exists():
        return f"assets/thumbs/{fname}"

    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            raw = resp.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        img.save(target, "JPEG", quality=quality, optimize=True)
        log.info("thumb_saved", extra={"file": fname, "platform": platform})
        return f"assets/thumbs/{fname}"
    except Exception as exc:
        log.warning("thumb_failed", extra={"url": url, "post_id": post_id, "error": str(exc)})
        return None


def replace_top5_media(data: dict[str, Any]) -> None:
    """Recorre data['<platform>']['top5'] y reemplaza media_url por path local."""
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = data.get(plat)
        if not block:
            continue
        for top in block.get("top5", []) or []:
            url = top.get("media_url")
            # Si ya es path local (assets/thumbs/...) lo dejamos
            if url and not url.startswith("assets/"):
                # post_id = url no estable; usamos url del post como hash key
                post_url = top.get("url") or url
                local = download_thumb(url, post_url, plat)
                if local:
                    top["media_url"] = local
                else:
                    top["media_url"] = ""
