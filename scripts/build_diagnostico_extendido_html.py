#!/usr/bin/env python3
"""Genera /diagnostico-extendido/index.html con DATA embebida desde Supabase
para el periodo 'diagnostico-extendido' (Ene-May 2026).

Estrategia: clona el HTML actual de /diagnostico/index.html (que ya funciona
bien con DATA embebida) y solo reemplaza:
  - El bloque `const DATA = {...}` con la data nueva de Supabase
  - El eyebrow / labels para reflejar la ventana real
  - REPORT_META para incluir el periodo nuevo en el dropdown

Costo: $0 (Supabase free tier, Gemini opcional aparte).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.load.supabase_client import Supabase
from pipeline.util.log import get_logger

log = get_logger("build-diag-ext")
CLIENT_ID = "comapan"
PERIOD_ID = "diagnostico-extendido"

ROOT = Path(__file__).resolve().parent.parent
SOURCE_HTML = ROOT / "diagnostico" / "index.html"
TARGET_DIR  = ROOT / "diagnostico-extendido"
TARGET_HTML = TARGET_DIR / "index.html"

PLATFORM_CAPS = {"instagram": "Instagram", "facebook": "Facebook",
                 "tiktok": "TikTok", "linkedin": "LinkedIn"}


def build_data_dict(sb: Supabase) -> dict:
    """Reconstruye el DATA dict canónico desde Supabase."""
    accounts_rows = sb.select("accounts",
        filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}")
    agg_rows = sb.select("aggregates",
        filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.{PERIOD_ID}")

    # --- accounts ---
    accounts: dict = {}
    for a in accounts_rows:
        plat_cap = PLATFORM_CAPS.get(a["platform"], a["platform"].capitalize())
        accounts[plat_cap] = {
            "bio": a.get("bio") or "",
            "business_account": str(a.get("is_business")) if a.get("is_business") is not None else "",
            "categoria": a.get("category") or "",
            "direccion": (a.get("raw") or {}).get("direccion") or "",
            "nombre": a.get("display_name") or "",
            "page_likes": str(a.get("page_likes")) if a.get("page_likes") is not None else "",
            "plataforma": plat_cap,
            "posts_totales": str(a.get("posts_total")) if a.get("posts_total") is not None else "",
            "rating": (a.get("raw") or {}).get("rating") or "",
            "seguidores": str(a.get("followers")) if a.get("followers") is not None else "",
            "siguiendo": str(a.get("following_n")) if a.get("following_n") is not None else "",
            "snapshot_fecha": (a.get("snapshot_at") or "")[:10],
            "telefono": (a.get("raw") or {}).get("telefono") or "",
            "url_externa": a.get("external_url") or "",
            "username": a.get("username") or "",
            "verified": str(a.get("verified")) if a.get("verified") is not None else "",
            "views_totales_90d": str(a.get("views_window")) if a.get("views_window") is not None else "",
            "website": a.get("website") or "",
        }

    # --- platform blocks (instagram, facebook, tiktok, linkedin) ---
    blocks: dict = {"instagram": {}, "facebook": {}, "tiktok": {}, "linkedin": {}}
    for a in agg_rows:
        plat = a["platform"]
        if plat not in blocks:
            continue
        name = a["metric_name"]
        val = a["metric_value"]
        if name == "engagement_stats" and isinstance(val, dict):
            blocks[plat].update(val)
        else:
            blocks[plat][name] = val

    # --- consolidated (1 fila por plataforma para la tabla) ---
    consolidated = []
    for plat, cap in PLATFORM_CAPS.items():
        b = blocks.get(plat) or {}
        acc = accounts.get(cap) or {}
        if not b and not acc:
            continue
        top5 = b.get("top5") or []
        top_post = top5[0] if top5 else {}
        consolidated.append({
            "plataforma": cap,
            "username": acc.get("username", ""),
            "seguidores": acc.get("seguidores", ""),
            "posts del periodo": str(b.get("n_posts") or 0),
            "engagement total": str(b.get("engagement_total") or 0),
            "engagement_promedio_post": str(round(b.get("engagement_promedio") or 0, 1)),
            "top_post_url": top_post.get("url", ""),
            "top_post_engagement": str(top_post.get("engagement") or 0),
            "snapshot_fecha": acc.get("snapshot_fecha", ""),
        })

    # --- snapshots_history (minimal, desde accounts) ---
    snapshots = []
    for cap, acc in accounts.items():
        if acc.get("seguidores"):
            snapshots.append({
                "snapshot_date": acc.get("snapshot_fecha", ""),
                "plataforma": cap,
                "metrica": "followers" if cap != "Facebook" else "page_likes",
                "valor": acc.get("seguidores") or acc.get("page_likes", ""),
                "posts_acumulados": acc.get("posts_totales", ""),
                "fuente": "apify",
            })

    return {
        "generated_at": "17/06/2026",
        "ventana": {"desde": "2026-01-01", "hasta": "2026-05-31"},
        "accounts": accounts,
        "consolidated": consolidated,
        "instagram": blocks["instagram"],
        "facebook":  blocks["facebook"],
        "tiktok":    blocks["tiktok"],
        "linkedin":  blocks["linkedin"],
        "fb_undated": 0,
        "fb_total":   blocks["facebook"].get("n_posts") or 0,
        "snapshots_history": snapshots,
        "periodo_label": "Diagnóstico ampliado · Ene-May 2026",
        "periodo_id":    "diagnostico-extendido",
    }


def main() -> int:
    sb = Supabase()
    print("→ Construyendo DATA desde Supabase…")
    data = build_data_dict(sb)

    print(f"  IG posts: {data['instagram'].get('n_posts')}")
    print(f"  FB posts: {data['facebook'].get('n_posts')}")
    print(f"  TT posts: {data['tiktok'].get('n_posts')}")
    print(f"  LI posts: {data['linkedin'].get('n_posts')}")

    # Leer template fuente (el HTML actual de /diagnostico/ que ya funciona)
    src = SOURCE_HTML.read_text()

    # Reemplazar el bloque `const DATA = {...};`
    data_json = json.dumps(data, ensure_ascii=False, separators=(', ', ': '))
    pattern = re.compile(r"const DATA = \{.*?\};", re.DOTALL)
    if not pattern.search(src):
        print("  ✗ No encontré 'const DATA = {...};' en el template fuente")
        return 1
    # Lambda evita que re.sub interprete \n, \g, etc. como secuencias especiales
    src = pattern.sub(lambda m: f"const DATA = {data_json};", src, count=1)
    print("  ✓ DATA reemplazado")

    # Actualizar REPORT_META.current y meter el nuevo periodo en available
    new_meta = {
        "current": "diagnostico-extendido",
        "available": [
            {"id": "diagnostico-extendido", "label": "Diagnóstico ampliado (Ene-May 2026)", "url": "/diagnostico-extendido/"},
            {"id": "diagnostico",           "label": "Diagnóstico inicial (Feb-Abr 2026)",   "url": "/diagnostico/"},
            {"id": "2026-06",               "label": "Junio 2026",                            "url": "/2026-06/"},
        ],
    }
    meta_json = json.dumps(new_meta, ensure_ascii=False)
    src = re.sub(r"const REPORT_META = \{.*?\};", lambda m: f"const REPORT_META = {meta_json};", src, count=1, flags=re.DOTALL)
    print("  ✓ REPORT_META reemplazado")

    # Escribir el nuevo archivo
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_HTML.write_text(src)
    print(f"\n✅ Generado: {TARGET_HTML.relative_to(ROOT)}")
    print(f"   Tamaño: {len(src):,} bytes")
    # También escribir como landing del root (sync automático)
    ROOT_HTML = ROOT / "index.html"
    ROOT_HTML.write_text(src)
    print(f"✅ Sincronizado a landing: {ROOT_HTML.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
