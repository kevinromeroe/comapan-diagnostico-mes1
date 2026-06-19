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
TARGET_DIR  = ROOT / "diagnostico"  # ahora SOBREESCRIBE el diagnostico/
TARGET_HTML = TARGET_DIR / "index.html"

PLATFORM_CAPS = {"instagram": "Instagram", "facebook": "Facebook",
                 "tiktok": "TikTok", "linkedin": "LinkedIn"}



# ─────────────────────────────────────────────────────────────
# ENRIQUECIMIENTOS — agregados que el build calcula desde posts
# ─────────────────────────────────────────────────────────────
from datetime import datetime as _dt, timezone as _tz, timedelta as _td
from collections import defaultdict

# America/Bogota = UTC-5 (no DST)
BOGOTA_TZ = _tz(_td(hours=-5))

def _to_bogota(ts):
    if ts is None: return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_tz.utc)
    return ts.astimezone(BOGOTA_TZ)

DOW_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

def _parse_ts(s):
    if not s: return None
    try:
        # ISO 8601 con Z o offset
        if s.endswith("Z"):
            return _dt.fromisoformat(s.replace("Z", "+00:00"))
        return _dt.fromisoformat(s)
    except Exception:
        return None

def enrich_by_hour_engagement(data, posts):
    """Recalcula counts + engagement_promedio por hora en zona Bogota (UTC-5)."""
    by_plat = defaultdict(list)
    for p in posts:
        by_plat[p["platform"]].append(p)
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = data.get(plat) or {}
        counts_by_hour = defaultdict(int)
        eng_by_hour    = defaultdict(list)
        for p in by_plat.get(plat, []):
            ts = _to_bogota(_parse_ts(p.get("posted_at")))
            if not ts: continue
            h = ts.hour
            counts_by_hour[h] += 1
            eng_by_hour[h].append(p.get("engagement") or 0)
        if not counts_by_hour:
            continue
        # Reconstruir labels ordenados (solo horas con posts, como en el agregador original)
        labels_sorted = sorted(counts_by_hour.keys())
        labels   = [str(h) for h in labels_sorted]
        counts   = [counts_by_hour[h] for h in labels_sorted]
        promedios = []
        for h in labels_sorted:
            arr = eng_by_hour.get(h, [])
            promedios.append(round(sum(arr) / len(arr), 1) if arr else 0)
        block["by_hour"] = {
            "labels": labels,
            "counts": counts,
            "engagement_promedio": promedios,
            "_timezone": "America/Bogota",
        }
        data[plat] = block

def enrich_by_day_hour_heatmap(data, posts):
    """Genera matriz 7×24 con engagement_promedio por (día semana, hora) por plataforma."""
    by_plat = defaultdict(list)
    for p in posts:
        by_plat[p["platform"]].append(p)
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        # matrix[dow][hour] = engagement_promedio
        matrix = [[0 for _ in range(24)] for _ in range(7)]
        counts = [[0 for _ in range(24)] for _ in range(7)]
        engs   = [[0 for _ in range(24)] for _ in range(7)]
        for p in by_plat.get(plat, []):
            ts = _to_bogota(_parse_ts(p.get("posted_at")))
            if not ts: continue
            dow = ts.weekday()  # 0=Lun … 6=Dom (en hora Bogota)
            h = ts.hour
            engs[dow][h] += p.get("engagement") or 0
            counts[dow][h] += 1
        for d in range(7):
            for h in range(24):
                if counts[d][h] > 0:
                    matrix[d][h] = round(engs[d][h] / counts[d][h], 1)
        block = data.get(plat) or {}
        block["by_day_hour"] = {
            "labels_dow":  DOW_LABELS,
            "labels_hour": [str(h) for h in range(24)],
            "matrix":      matrix,
            "counts":      counts,
        }
        data[plat] = block

def gemini_per_post_insights(data, api_key, max_retries=2):
    """Para cada top5 de cada plataforma, genera 1 frase: por qué funcionó."""
    if not api_key:
        print("  ⚠ GEMINI_API_KEY no presente, saltando insights por post")
        return
    import urllib.request, urllib.error, json as _json
    URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = data.get(plat) or {}
        top5 = block.get("top5") or []
        for i, post in enumerate(top5):
            caption = (post.get("caption") or "")[:200]
            eng     = post.get("engagement") or 0
            likes   = post.get("likes") or 0
            coms    = post.get("comentarios") or 0
            tipo    = post.get("tipo") or "post"
            prompt = (
                f"Eres analista de social media corporativo. Analiza por qué este "
                f"post de Comapan ({plat}) tuvo {eng} interacciones ({likes} likes, "
                f"{coms} comentarios). Tipo: {tipo}. Caption: \"{caption}\". "
                f"Responde en UNA sola frase de máximo 25 palabras, español neutro "
                f"SIN acentos diacríticos, foco accionable para el equipo creativo."
            )
            body = {"contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 100}}
            req = urllib.request.Request(
                f"{URL}?key={api_key}",
                data=_json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = _json.loads(r.read())
                    insight = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # limpiar comillas o markdown
                    insight = insight.strip('"\'').replace("\n", " ").strip()
                    post["insight"] = insight
            except Exception as exc:
                print(f"    ⚠ Gemini insight failed for {plat}[{i}]: {exc}")
                post["insight"] = ""
        print(f"  ✓ {plat}: {len([p for p in top5 if p.get('insight')])}/{len(top5)} insights generados")


def build_data_dict(sb: Supabase) -> dict:
    """Construye DATA desde la tabla `posts` (no depende de aggregates).

    Lee:
      - accounts del periodo "diagnostico" (snapshot mas reciente disponible)
      - posts del cliente filtrados a ventana Ene-May 2026
    Calcula todos los agregados al vuelo en zona America/Bogota.
    """
    # Imports locales para evitar costos al cargar
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td_local
    from collections import Counter as _Counter

    BG = _tz(_td_local(hours=-5))  # America/Bogota
    START = _dt(2026, 1, 1,  tzinfo=BG)
    END   = _dt(2026, 5, 31, 23, 59, 59, tzinfo=BG)

    def _to_bg(s):
        if not s: return None
        try:
            t = _dt.fromisoformat(s.replace("Z", "+00:00")) if s.endswith("Z") else _dt.fromisoformat(s)
            if t.tzinfo is None: t = t.replace(tzinfo=_tz.utc)
            return t.astimezone(BG)
        except Exception:
            return None

    # --- accounts (snapshot vigente) ---
    accounts_rows = sb.select("accounts",
        filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.diagnostico")
    accounts: dict = {}
    for a in accounts_rows:
        cap = PLATFORM_CAPS.get(a["platform"], a["platform"].capitalize())
        accounts[cap] = {
            "bio": a.get("bio") or "",
            "business_account": str(a.get("is_business")) if a.get("is_business") is not None else "",
            "categoria": a.get("category") or "",
            "direccion": (a.get("raw") or {}).get("direccion") or "",
            "nombre": a.get("display_name") or "",
            "page_likes": str(a.get("page_likes")) if a.get("page_likes") is not None else "",
            "plataforma": cap,
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

    # --- posts filtrados ---
    posts_rows = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")
    print(f"  Posts totales en Supabase: {len(posts_rows)}")
    posts_bg = []
    for r in posts_rows:
        ts = _to_bg(r.get("posted_at"))
        if not ts or ts < START or ts > END:
            continue
        posts_bg.append({
            "platform":   r.get("platform"),
            "id":         r.get("id"),
            "url":        r.get("url") or "",
            "type":       r.get("type") or "post",
            "caption":    r.get("caption") or "",
            "hashtags":   r.get("hashtags") or [],
            "likes":      r.get("likes") or 0,
            "comments":   r.get("comments") or 0,
            "shares":     r.get("shares") or 0,
            "engagement": r.get("engagement") or 0,
            "media_url":  r.get("media_url") or "",
            "ts":         ts,
        })
    print(f"  Posts en ventana Ene-May (Bogota): {len(posts_bg)}")

    DOW = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
    blocks: dict = {"instagram": {}, "facebook": {}, "tiktok": {}, "linkedin": {}}

    for plat in ("instagram","facebook","tiktok","linkedin"):
        ps = [p for p in posts_bg if p["platform"] == plat]
        n = len(ps)
        if n == 0:
            blocks[plat] = {
                "n_posts": 0, "engagement_total": 0, "engagement_promedio": 0, "engagement_mediana": 0,
                "by_type": {"labels": [], "counts": [], "engagement": [], "engagement_promedio": []},
                "by_day":  {"labels": DOW, "counts": [0]*7, "engagement_promedio": [0]*7},
                "by_hour": {"labels": [], "counts": [], "engagement_promedio": [], "_timezone": "America/Bogota"},
                "by_week": {"labels": [], "counts": [], "engagement": []},
                "captions_avg_len": 0, "top_hashtags": [], "top5": [],
            }
            continue

        engs = [p["engagement"] for p in ps]
        total_eng = sum(engs)
        prom = round(total_eng / n, 1)
        med = sorted(engs)[n // 2]

        # by_type
        type_counts = _Counter()
        type_engs   = _Counter()
        for p in ps:
            t = p["type"] or "post"
            type_counts[t] += 1
            type_engs[t]   += p["engagement"]
        type_labels = sorted(type_counts.keys(), key=lambda t: -type_counts[t])
        by_type = {
            "labels": type_labels,
            "counts": [type_counts[t] for t in type_labels],
            "engagement": [type_engs[t] for t in type_labels],
            "engagement_promedio": [round(type_engs[t]/type_counts[t], 1) for t in type_labels],
        }

        # by_day (0=Lun)
        day_counts = [0]*7
        day_engs   = [0]*7
        for p in ps:
            d = p["ts"].weekday()
            day_counts[d] += 1
            day_engs[d]   += p["engagement"]
        by_day = {
            "labels": DOW,
            "counts": day_counts,
            "engagement_promedio": [round(day_engs[i]/day_counts[i], 1) if day_counts[i] else 0 for i in range(7)],
        }

        # by_hour (Bogota) - solo horas con posts, ordenadas
        h_counts = _Counter()
        h_engs   = _Counter()
        for p in ps:
            h = p["ts"].hour
            h_counts[h] += 1
            h_engs[h]   += p["engagement"]
        h_sorted = sorted(h_counts.keys())
        by_hour = {
            "labels": [str(h) for h in h_sorted],
            "counts": [h_counts[h] for h in h_sorted],
            "engagement_promedio": [round(h_engs[h]/h_counts[h], 1) for h in h_sorted],
            "_timezone": "America/Bogota",
        }

        # by_week (formato 2026-Sxx)
        week_counts = _Counter()
        week_engs   = _Counter()
        for p in ps:
            iso = p["ts"].isocalendar()
            wk = f"{iso[0]}-S{iso[1]:02d}"
            week_counts[wk] += 1
            week_engs[wk]   += p["engagement"]
        wk_sorted = sorted(week_counts.keys())
        by_week = {
            "labels": wk_sorted,
            "counts": [week_counts[w] for w in wk_sorted],
            "engagement": [week_engs[w] for w in wk_sorted],
        }

        # top_hashtags
        hash_count = _Counter()
        for p in ps:
            for tag in (p.get("hashtags") or []):
                if tag: hash_count[tag] += 1
        top_hashtags = hash_count.most_common(10)

        # captions_avg_len
        captions_avg_len = round(sum(len(p["caption"] or "") for p in ps) / n, 1)

        # top5 por engagement
        ps_sorted = sorted(ps, key=lambda p: -p["engagement"])[:5]
        top5 = [{
            "url":         p["url"],
            "tipo":        p["type"],
            "fecha":       p["ts"].strftime("%Y-%m-%d"),
            "likes":       p["likes"],
            "caption":     p["caption"],
            "media_url":   p["media_url"],
            "engagement":  p["engagement"],
            "comentarios": p["comments"],
        } for p in ps_sorted]

        blocks[plat] = {
            "n_posts": n,
            "engagement_total": total_eng,
            "engagement_promedio": prom,
            "engagement_mediana": med,
            "by_type": by_type,
            "by_day":  by_day,
            "by_hour": by_hour,
            "by_week": by_week,
            "captions_avg_len": captions_avg_len,
            "top_hashtags": top_hashtags,
            "top5": top5,
        }

    # --- consolidated (una fila por red) ---
    consolidated = []
    for plat, cap in PLATFORM_CAPS.items():
        b = blocks.get(plat) or {}
        acc = accounts.get(cap) or {}
        if not b.get("n_posts"): continue
        t5 = b.get("top5") or []
        top_post = t5[0] if t5 else {}
        consolidated.append({
            "plataforma": cap,
            "username": acc.get("username", ""),
            "seguidores": acc.get("seguidores", ""),
            "posts del periodo": str(b.get("n_posts") or 0),
            "engagement total":  str(b.get("engagement_total") or 0),
            "engagement_promedio_post": str(b.get("engagement_promedio") or 0),
            "top_post_url": top_post.get("url",""),
            "top_post_engagement": str(top_post.get("engagement") or 0),
            "snapshot_fecha": acc.get("snapshot_fecha",""),
        })

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

    # Heatmap (matriz dia x hora) — agregado adicional desde los posts ya parseados
    print("→ Generando heatmap dia x hora + insights LLM…")
    try:
        posts = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")
        enrich_by_day_hour_heatmap(data, posts)
        print("  ✓ by_day_hour heatmap agregado (Bogota)")
        import os
        gemini_per_post_insights(data, os.environ.get("GEMINI_API_KEY"))
    except Exception as exc:
        print(f"  ⚠ Enriquecimiento parcial fallo: {exc}")


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
        "current": "diagnostico",
        "available": [
            {"id": "diagnostico", "label": "Diagnóstico (Ene-May 2026)", "url": "/diagnostico/"},
            {"id": "2026-06",     "label": "Junio 2026",                  "url": "/2026-06/"},
        ],
    }
    meta_json = json.dumps(new_meta, ensure_ascii=False)
    src = re.sub(r"const REPORT_META = \{.*?\};", lambda m: f"const REPORT_META = {meta_json};", src, count=1, flags=re.DOTALL)
    print("  ✓ REPORT_META reemplazado")

    # Escribir el nuevo archivo
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    # Post-process: arreglar strings hardcoded del template antiguo
    for old_s, new_s in [
        ("Feb a Abr 2026", "Ene a May 2026"),
        ("Feb-Abr 2026",   "Ene-May 2026"),
        ("feb a abr 2026", "ene a may 2026"),
        ("feb-abr 2026",   "ene-may 2026"),
        ("Feb-Abr",        "Ene-May"),
    ]:
        src = src.replace(old_s, new_s)
    # Fix bug 'd is not defined' por si vuelve a aparecer
    src = src.replace(
        'kpi("Posts publicados", fmt(d.n_posts)',
        'kpi("Posts publicados", fmt(data.n_posts)'
    )
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
