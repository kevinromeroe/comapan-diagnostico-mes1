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

TAG_TAXONOMY = [
    "producto",      # Showcase de un producto puntual
    "receta",        # Receta o uso del producto
    "ugc",           # User-generated content / repost
    "estacional",    # Dias especiales (Dia Mujer, Madre, etc)
    "tendencia",     # Pop culture, meme, trending audio
    "marca",         # Storytelling corporativo, valores
    "promocional",   # Descuentos, lanzamientos, ofertas
    "educativo",     # Tips, datos curiosos
    "cultura",       # Empleados, behind the scenes
    "interaccion",   # Preguntas a la audiencia, encuestas
    "cobranding",    # Colab con otra marca o influencer
    "humor",         # Tono comico
]


def _guess_tag_from_caption(caption: str) -> str:
    """Fallback inteligente: intenta deducir la categoria por keywords del caption.
    Solo se usa cuando Gemini falla — para que ningun post quede como 'marca' vacio.
    """
    c = (caption or "").lower()
    # Recetas: mencion de preparar/cocinar con el producto
    if any(w in c for w in ["receta", "ingredientes", "preparacion", "preparación", "prepara",
                             "mezclar", "cocina", "hornea", "unta", "rellena", "sirve", "combinar"]):
        return "receta"
    # Promocional: descuentos, ofertas, concursos
    if any(w in c for w in ["descuento", "promo", "% off", "oferta", "gratis", "concurso",
                             "gana", "sorteo", "$"]):
        return "promocional"
    # Interaccion: preguntas a la audiencia
    if any(w in c for w in ["cuentanos", "cuéntanos", "cual es tu", "cuál es tu", "coméntanos",
                             "comentanos", "cual prefieres", "cuál prefieres", "responde",
                             "opinen", "opinas"]):
        return "interaccion"
    # Estacional: dia especial o efeméride
    if any(w in c for w in ["dia de", "día de", "dia mundial", "día mundial", "dia internacional",
                             "día internacional", "feliz cumple", "san valentin", "san valentín",
                             "amor y amistad", "navidad", "halloween", "mundial", "final",
                             "champions"]):
        return "estacional"
    # UGC: repost / gracias
    if any(w in c for w in ["repost", "reposteo", "@usuario", "muchas gracias por", "compartes con",
                             "muestrenos", "muéstrennos"]):
        return "ugc"
    # Educativo: tips / datos
    if any(w in c for w in ["sabias que", "sabías que", "sabías", "sabias", "dato curioso",
                             "tip", "trucos", "como hacer", "cómo hacer"]):
        return "educativo"
    # Cultura: equipo, colaboradores, oficina
    if any(w in c for w in ["equipo", "colaboradores", "oficina", "planta", "trabajadores",
                             "empleados", "nuestra gente"]):
        return "cultura"
    # Producto: mencion de producto especifico Comapan
    if any(w in c for w in ["comapan", "pan tajado", "pancake", "brownie", "mantecada", "muffin",
                             "sanduche", "sandwich", "arepa", "caladitos", "ponque", "ponqué",
                             "pastel", "torta", "galleta"]):
        return "producto"
    # Ultimo recurso
    return "marca"


def _apply_keyword_fallback(batch):
    """Aplica _guess_tag_from_caption a cada post del batch (cuando Gemini fallo)."""
    counts = {}
    for it in batch:
        tag = _guess_tag_from_caption(it.get("caption", ""))
        it["ref"]["tags"] = [tag]
        it["ref"]["tag_primary"] = tag
        counts[tag] = counts.get(tag, 0) + 1
    top = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
    print(f"       Fallback keyword: {len(batch)} posts distribuidos → {top}")


def gemini_tag_posts_batched(data, api_key, sb=None, batch_size=25):
    """Etiqueta posts NO etiquetados aun. Persiste tags en Supabase para reuso."""
    if not api_key:
        print("  ❌ FATAL: GEMINI_API_KEY no presente. Verificar secret en GitHub.")
        raise RuntimeError("GEMINI_API_KEY missing")
    print(f"  GEMINI_API_KEY presente (len={len(api_key)} chars, prefijo={api_key[:6]}…)")

    import urllib.request, urllib.error, json as _json, re as _re
    URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    # Recolectar todos los posts de las 4 plataformas + top5 (las top5 ya estan en blocks)
    # Pero queremos etiquetar TODOS los posts. Para eso volvemos a leer posts y usamos
    # un mapeo por post["id"] o (plat, url).
    # Estrategia simpler: hacer tagging SOLO sobre top5 de cada plataforma porque para
    # el chart de "engagement por categoria" con ALL posts necesitariamos sus captions
    # tambien, lo cual incrementa los tokens. Hago 2 pasadas si nos sobra cuota.
    #
    # Aqui hacemos top5 (max 20 posts) + tantos posts adicionales como se pueda en
    # los batches restantes. Configurable.

    # Construir cola de posts: priorizamos top5 por plataforma, luego el resto en orden
    # (el caller debe poner posts crudos en data["_all_posts_for_tagging"] si quiere todo)
    queue = []
    seen = set()
    already = 0
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = data.get(plat) or {}
        for i, post in enumerate(block.get("top5") or []):
            key = (plat, post.get("url") or post.get("id") or f"{plat}-{i}")
            if key in seen: continue
            seen.add(key)
            # Si ya tiene tag_primary persistido, lo respetamos y NO llamamos a Gemini
            if post.get("tag_primary"):
                already += 1
                continue
            queue.append({
                "key": key, "plat": plat, "ref": post,
                "tipo": post.get("tipo") or "post",
                "caption": (post.get("caption") or "")[:400],
                "post_id": None,  # top5 no tiene id directo
            })

    extra = data.pop("__all_posts_for_tagging", [])
    for ex in extra:
        if ex["key"] in seen: continue
        seen.add(ex["key"])
        # Saltar si ya tiene tag_primary
        if ex.get("ref", {}).get("tag_primary"):
            already += 1
            continue
        # Para los posts extra, podemos rastrear el id si esta en ref
        ex["post_id"] = ex.get("ref", {}).get("id")
        queue.append(ex)

    print(f"  Posts ya etiquetados (skip): {already}")
    print(f"  Posts a etiquetar ahora: {len(queue)} en batches de {batch_size}")
    if not queue:
        print("  ✓ Todos los posts ya tienen tag persistido — sin llamadas a Gemini")

    taxonomy_str = ", ".join(TAG_TAXONOMY)

    for start in range(0, len(queue), batch_size):
        batch = queue[start:start+batch_size]
        batch_num = start//batch_size + 1
        post_lines = []
        for j, p_item in enumerate(batch):
            post_lines.append(
                f"#{j} [{p_item['plat']} {p_item['tipo']}] {p_item['caption']}"
            )

        prompt = (
            "Clasifica cada publicacion de Comapan (panaderia colombiana en Colombia). "
            "Asigna UNA etiqueta primaria obligatoria y entre 0 y 2 secundarias. "
            "TAXONOMIA CERRADA (no inventes): " + taxonomy_str + ". "
            "REGLA IMPORTANTE: usa 'marca' SOLO cuando el post sea storytelling corporativo "
            "sobre historia, valores o mision (ej. 'llevamos 75 anos endulzando hogares'). "
            "Si el post menciona un producto especifico usar en el caption (pan tajado, "
            "brownie, pancake, mantecada, muffin, arepa, sanduche, etc.) usa 'producto'. "
            "Si describe como preparar algo usando el producto → 'receta'. "
            "Si es sobre Mundial, dia especial, fecha conmemorativa → 'estacional' o 'tendencia'. "
            "Si es pregunta o encuesta → 'interaccion'. "
            "Definiciones rapidas: producto=showcase de un item especifico; "
            "receta=cocinar con el producto; ugc=repost de cliente; "
            "estacional=fechas especiales (Dia Mujer, etc); tendencia=meme/pop; "
            "marca=storytelling corporativo; promocional=descuento/lanzamiento; "
            "educativo=tip o dato; cultura=empleados; interaccion=pregunta a la audiencia; "
            "cobranding=colab con otra marca; humor=tono comico. "
            "Devuelve SOLO JSON sin markdown: "
            '{"items":[{"i":0,"primary":"producto","secondary":["humor"]},...]}\n\n'
            "Posts:\n" + "\n".join(post_lines)
        )

        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 8000,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }
        req = urllib.request.Request(
            f"{URL}?key={api_key}",
            data=_json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status = r.status
                raw_body = r.read()
                resp = _json.loads(raw_body)
                # diagnostico: finishReason + tokens
                fr = (resp.get("candidates") or [{}])[0].get("finishReason")
                um = resp.get("usageMetadata") or {}
                if fr and fr != "STOP":
                    print(f"  ⚠ Batch {start//batch_size + 1}: finishReason={fr} prompt={um.get('promptTokenCount')} resp={um.get('candidatesTokenCount')} thoughts={um.get('thoughtsTokenCount')}")
                try:
                    txt = resp["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError) as e:
                    print(f"    ⚠ Batch {start//batch_size + 1}: shape de respuesta inesperada (status={status} finishReason={fr})")
                    print(f"       Usage: {um}")
                    print(f"       Resp keys: {list(resp.keys())}")
                    print(f"       Resp[:500]: {str(resp)[:500]}")
                    continue
                try:
                    parsed = _json.loads(txt)
                except Exception as e:
                    print(f"    ⚠ Batch {start//batch_size + 1}: JSON parse falló de la respuesta de Gemini")
                    print(f"       Texto Gemini: {txt[:300]}")
                    continue
                items = parsed.get("items") or []
                ok_count = 0
                upsert_rows = []
                from datetime import datetime as _dtnow, timezone as _tzn
                now_iso = _dtnow.now(_tzn.utc).isoformat()
                for it in items:
                    idx = it.get("i")
                    if idx is None or idx >= len(batch): continue
                    primary = (it.get("primary") or "").lower().strip()
                    if primary not in TAG_TAXONOMY:
                        primary = _guess_tag_from_caption(batch[idx].get("caption", ""))
                    secondary = [t.lower().strip() for t in (it.get("secondary") or [])
                                 if t.lower().strip() in TAG_TAXONOMY and t.lower().strip() != primary][:2]
                    full_tags = [primary] + secondary
                    batch[idx]["ref"]["tags"] = full_tags
                    batch[idx]["ref"]["tag_primary"] = primary
                    ok_count += 1
                    # Persistir a Supabase si tenemos post_id
                    pid = batch[idx].get("post_id")
                    if sb is not None and pid:
                        upsert_rows.append({
                            "id":          pid,
                            "tags":        full_tags,
                            "tag_primary": primary,
                            "tagged_at":   now_iso,
                        })
                if sb is not None and upsert_rows:
                    try:
                        sb.upsert("posts", upsert_rows, on_conflict="id")
                        print(f"  ✓ Batch {start//batch_size + 1}: {ok_count}/{len(batch)} tags + {len(upsert_rows)} persistidos a Supabase")
                    except Exception as exc:
                        print(f"  ⚠ Batch {start//batch_size + 1}: tags OK pero falló persistir a Supabase: {exc}")
                else:
                    print(f"  ✓ Batch {start//batch_size + 1}: {ok_count}/{len(batch)} posts etiquetados (sin persistir)")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")[:600]
            print(f"    ⚠ Batch {batch_num}: HTTPError {e.code}")
            print(f"       Body: {err_body}")
            _apply_keyword_fallback(batch)
        except Exception as exc:
            print(f"    ⚠ Batch {batch_num}: {type(exc).__name__}: {exc}")
            _apply_keyword_fallback(batch)

    # Pre-agregar usando TODOS los posts en queue (no solo top5)
    from collections import defaultdict
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = data.get(plat) or {}
        plat_tagged = [q for q in queue if q["plat"] == plat and q["ref"].get("tag_primary")]
        block["tag_summary"]    = {}
        block["tag_engagement"] = {}
        if plat_tagged:
            counts  = defaultdict(int)
            eng_sum = defaultdict(int)
            eng_n   = defaultdict(int)
            for q in plat_tagged:
                primary = q["ref"]["tag_primary"]
                eng     = q["ref"].get("engagement", 0)
                counts[primary]  += 1
                eng_sum[primary] += eng
                eng_n[primary]   += 1
            block["tag_summary"]    = dict(counts)
            block["tag_engagement"] = {k: round(eng_sum[k]/eng_n[k], 1) for k in eng_n if eng_n[k] > 0}
        data[plat] = block
        print(f"  {plat}: {len(plat_tagged)} posts taggeados → {len(block['tag_summary'])} categorias")


def compute_category_analysis(data, sb):
    """Aggrega los 298 posts por categoria para el nuevo tab de Analisis por categorias."""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from collections import defaultdict
    import statistics as _stats

    BG = _tz(_td(hours=-5))
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

    print("\n→ Computando category_analysis…")
    posts = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")
    print(f"  sb.select(\"posts\") → {len(posts)} filas")
    if posts:
        sample = posts[0]
        print(f"  Muestra fila[0]: keys={list(sample.keys())[:10]}")
        print(f"    posted_at = {sample.get('posted_at')!r}")
        print(f"    tag_primary = {sample.get('tag_primary')!r}")
        print(f"    engagement = {sample.get('engagement')!r}")

    posts_in = []
    skipped_no_ts = 0
    skipped_out_window = 0
    skipped_no_tag = 0
    for r in posts:
        ts = _to_bg(r.get("posted_at"))
        if not ts:
            skipped_no_ts += 1; continue
        if ts < START or ts > END:
            skipped_out_window += 1; continue
        if not r.get("tag_primary"):
            skipped_no_tag += 1; continue
        posts_in.append({
            "category": r["tag_primary"],
            "platform": r.get("platform") or "",
            "type":     r.get("type") or "post",
            "engagement": r.get("engagement") or 0,
        })
    print(f"  posts_in: {len(posts_in)} | skip(sin ts)={skipped_no_ts} | skip(fuera ventana)={skipped_out_window} | skip(sin tag)={skipped_no_tag}")

    # FALLBACK: si Supabase no devuelve posts taggeados, usar lo que ya está en DATA
    # (top5+atipicos+worst5 fueron taggeados via propagate_tags_to_data y tienen fallback "marca")
    if not posts_in:
        print("  ⚠ posts_in vacío. Activando fallback desde DATA (top5+atipicos+worst5).")
        for plat in ("instagram", "facebook", "tiktok", "linkedin"):
            block = data.get(plat) or {}
            for lst_name in ("top5", "atipicos", "worst5"):
                for post in (block.get(lst_name) or []):
                    primary = post.get("tag_primary")
                    if not primary:
                        continue
                    posts_in.append({
                        "category": primary,
                        "platform": plat,
                        "type":     post.get("tipo") or "post",
                        "engagement": post.get("engagement") or 0,
                    })
        print(f"  Fallback: {len(posts_in)} posts desde DATA")

    if not posts_in:
        print("  ⚠ Sin posts con tag_primary en ningún lado. category_analysis quedará vacío.")
        data["category_analysis"] = {}
        return

    total = len(posts_in)
    global_mean = sum(p["engagement"] for p in posts_in) / total

    # A) Mix global
    cat_counts = defaultdict(int)
    for p in posts_in:
        cat_counts[p["category"]] += 1
    mix_global = sorted([
        {"category": c, "count": n, "pct": round(n / total * 100, 1)}
        for c, n in cat_counts.items()
    ], key=lambda x: -x["count"])

    # B) Performance por categoria (n, mean, median, p75)
    cat_engs = defaultdict(list)
    for p in posts_in:
        cat_engs[p["category"]].append(p["engagement"])
    performance = []
    for c, engs in cat_engs.items():
        engs_sorted = sorted(engs)
        n = len(engs)
        performance.append({
            "category": c,
            "n":        n,
            "mean":     round(sum(engs) / n, 1),
            "median":   _stats.median(engs),
            "p75":      engs_sorted[int(n * 0.75)] if n > 1 else engs_sorted[0],
        })
    performance.sort(key=lambda x: -x["mean"])

    # C) Categoria x Red — engagement promedio
    plats = ["instagram", "facebook", "tiktok", "linkedin"]
    cat_plat_eng = defaultdict(lambda: defaultdict(list))
    for p in posts_in:
        cat_plat_eng[p["category"]][p["platform"]].append(p["engagement"])
    categories_ordered = [m["category"] for m in mix_global]
    matrix_plat = []
    for c in categories_ordered:
        row = []
        for plat in plats:
            engs = cat_plat_eng[c].get(plat, [])
            row.append(round(sum(engs) / len(engs), 1) if engs else 0)
        matrix_plat.append(row)

    # D) Categoria x Tipo de media
    types_set = sorted({p["type"] for p in posts_in if p["type"]})
    cat_type_eng = defaultdict(lambda: defaultdict(list))
    for p in posts_in:
        cat_type_eng[p["category"]][p["type"]].append(p["engagement"])
    matrix_type = []
    for c in categories_ordered:
        row = []
        for t in types_set:
            engs = cat_type_eng[c].get(t, [])
            row.append(round(sum(engs) / len(engs), 1) if engs else 0)
        matrix_type.append(row)

    # E) Gaps estrategicos: oportunidades de escalar contenido
    # Criterio mas inclusivo: top 4 categorias por engagement entre las que tienen
    # mix bajo (<10%). Permite ver oportunidades aunque no superen el promedio global.
    gaps = []
    perf_by_cat = {pf["category"]: pf["mean"] for pf in performance}
    # Sortear por engagement promedio descendente, filtrando mix < 10%
    candidates = [m for m in mix_global if m["pct"] < 10.0]
    candidates_with_eng = [
        {"category": m["category"], "pct_of_mix": m["pct"], "count": m["count"],
         "avg_engagement": perf_by_cat.get(m["category"], 0)}
        for m in candidates
    ]
    candidates_with_eng.sort(key=lambda x: -x["avg_engagement"])
    # Tomamos hasta 5 — siempre que tengan engagement > 0
    for c in candidates_with_eng[:5]:
        if c["avg_engagement"] > 0:
            c["vs_global"] = round(c["avg_engagement"] / global_mean, 2)
            gaps.append(c)

    data["category_analysis"] = {
        "total_posts":   total,
        "global_mean":   round(global_mean, 1),
        "mix_global":    mix_global,
        "performance":   performance,
        "by_platform":   {"categories": categories_ordered, "platforms": plats, "matrix": matrix_plat},
        "by_type":       {"categories": categories_ordered, "types": types_set,  "matrix": matrix_type},
        "gaps":          gaps,
    }
    print(f"  ✓ category_analysis: {total} posts, {len(mix_global)} categorias, {len(gaps)} gaps")


def _previous_period(period: str) -> str | None:
    """Retorna el ID del mes anterior. None si es diagnostico o formato invalido."""
    if period == "diagnostico":
        return None
    try:
        y, m = period.split("-")
        yi, mi = int(y), int(m)
        if mi == 1:
            return f"{yi-1}-12"
        return f"{yi:04d}-{mi-1:02d}"
    except Exception:
        return None


def _aggregate_posts_for_window(sb, start, end) -> dict:
    """Lee posts en ventana Bogota y devuelve totales por plataforma."""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from collections import defaultdict
    BG = _tz(_td(hours=-5))
    def _to_bg(s):
        if not s: return None
        try:
            t = _dt.fromisoformat(s.replace("Z", "+00:00")) if s.endswith("Z") else _dt.fromisoformat(s)
            if t.tzinfo is None: t = t.replace(tzinfo=_tz.utc)
            return t.astimezone(BG)
        except Exception:
            return None
    posts = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")
    by_plat = defaultdict(list)
    for r in posts:
        ts = _to_bg(r.get("posted_at"))
        if not ts or ts < start or ts > end:
            continue
        by_plat[r.get("platform")].append(r.get("engagement") or 0)
    out = {}
    for plat, engs in by_plat.items():
        n = len(engs)
        te = sum(engs)
        out[plat] = {
            "n_posts": n,
            "engagement_total": te,
            "engagement_promedio": round(te / n, 1) if n else 0,
            "engagement_mediana": sorted(engs)[n // 2] if n else 0,
        }
    return out


def compute_deltas(data, sb, period):
    """Calcula deltas MoM vs el mes anterior. Diagnostico → sin deltas.

    Attach a data["deltas"] con:
      { "global":   {"total_posts_pct": +X, "total_engagement_pct": +X, ...},
        "instagram":{"n_posts_pct": +X, "engagement_total_pct": +X, "followers_pct": +X, ...},
        ...
      }
    """
    prev = _previous_period(period)
    if not prev:
        data["deltas"] = None
        print("  Sin periodo anterior — deltas omitidos (baseline)")
        return

    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    import calendar as _cal
    BG = _tz(_td(hours=-5))
    y, m = prev.split("-")
    yi, mi = int(y), int(m)
    START_PREV = _dt(yi, mi, 1, tzinfo=BG)
    END_PREV   = _dt(yi, mi, _cal.monthrange(yi, mi)[1], 23, 59, 59, tzinfo=BG)

    prev_metrics = _aggregate_posts_for_window(sb, START_PREV, END_PREV)
    print(f"  Deltas vs {prev}: {sum(v['n_posts'] for v in prev_metrics.values())} posts en periodo anterior")

    def _pct(cur, prev):
        if prev is None or prev == 0:
            return None if cur == 0 else 100.0  # infinito → 100 (arriba desde cero)
        return round(((cur - prev) / prev) * 100, 1)

    deltas = {"global": {}, "instagram": {}, "facebook": {}, "tiktok": {}, "linkedin": {}}

    # Leer accounts del periodo anterior (para comparar seguidores)
    PLAT_CAP = {"instagram":"Instagram", "facebook":"Facebook", "tiktok":"TikTok", "linkedin":"LinkedIn"}
    prev_accounts_rows = sb.select("accounts",
        filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.{prev}")
    if not prev_accounts_rows:
        # Fallback: si el mes anterior no tiene accounts registrados, usar el snapshot del diagnostico
        prev_accounts_rows = sb.select("accounts",
            filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.diagnostico")
        print(f"  (accounts prev no encontrados en '{prev}', usando snapshot de diagnostico)")
    prev_audience = {}
    for a in prev_accounts_rows:
        plat = a["platform"]
        # Facebook: comparar page_likes; el resto: followers
        val = a.get("page_likes") if plat == "facebook" else a.get("followers")
        prev_audience[plat] = val

    # Per platform
    total_cur_posts = 0
    total_cur_eng = 0
    total_prev_posts = 0
    total_prev_eng = 0
    for plat in ("instagram","facebook","tiktok","linkedin"):
        cur_b = data.get(plat) or {}
        cur_n = cur_b.get("n_posts") or 0
        cur_et = cur_b.get("engagement_total") or 0
        cur_ep = cur_b.get("engagement_promedio") or 0
        cur_em = cur_b.get("engagement_mediana") or 0
        prev_b = prev_metrics.get(plat) or {}
        prev_n = prev_b.get("n_posts") or 0
        prev_et = prev_b.get("engagement_total") or 0
        prev_ep = prev_b.get("engagement_promedio") or 0
        prev_em = prev_b.get("engagement_mediana") or 0

        # Audiencia (seguidores o page_likes)
        cap = PLAT_CAP[plat]
        acc_cur = (data.get("accounts") or {}).get(cap) or {}
        cur_aud = None
        try:
            key = "page_likes" if plat == "facebook" else "seguidores"
            v = acc_cur.get(key)
            if v not in (None, ""):
                cur_aud = int(v)
        except Exception:
            cur_aud = None
        prev_aud = prev_audience.get(plat)
        # Prev viene como int/None desde Supabase
        try:
            prev_aud = int(prev_aud) if prev_aud not in (None, "") else None
        except Exception:
            prev_aud = None
        audience_pct = _pct(cur_aud, prev_aud) if (cur_aud is not None and prev_aud is not None) else None

        deltas[plat] = {
            "n_posts_pct":            _pct(cur_n,  prev_n),
            "engagement_total_pct":   _pct(cur_et, prev_et),
            "engagement_promedio_pct":_pct(cur_ep, prev_ep),
            "engagement_mediana_pct": _pct(cur_em, prev_em),
            "audience_pct":           audience_pct,
        }
        total_cur_posts += cur_n
        total_cur_eng   += cur_et
        total_prev_posts += prev_n
        total_prev_eng   += prev_et

    # Global (resumen ejecutivo)
    cur_prom = round(total_cur_eng / total_cur_posts, 1) if total_cur_posts else 0
    prev_prom = round(total_prev_eng / total_prev_posts, 1) if total_prev_posts else 0
    deltas["global"] = {
        "total_posts_pct":         _pct(total_cur_posts, total_prev_posts),
        "total_engagement_pct":    _pct(total_cur_eng, total_prev_eng),
        "engagement_por_post_pct": _pct(cur_prom, prev_prom),
    }

    data["deltas"] = deltas
    data["_prev_period_label"] = prev
    print(f"  ✓ Deltas computados vs {prev}")


def propagate_tags_to_data(data, sb):
    """Despues del tagging, re-pull tags desde Supabase y aplicar a top5/atipicos/worst5.

    Solucion al bug: blocks[plat]["atipicos|worst5"] son copias hechas via _post_dict
    ANTES del tagging. El tagger modifica posts_bg pero no propaga a estas copias.
    Aqui leemos posts taggeados de Supabase y los aplicamos por post_id.
    """
    rows = sb.select("posts", filter="client_id=eq.comapan&select=id,tags,tag_primary")
    tag_map = {r["id"]: (r.get("tags"), r.get("tag_primary")) for r in rows if r.get("tag_primary")}
    print(f"  Propagando tags a top5/atipicos/worst5 desde {len(tag_map)} posts en Supabase…")

    total_propagated = 0
    total_missing    = 0
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        block = data.get(plat) or {}
        for lst_name in ("top5", "atipicos", "worst5"):
            posts = block.get(lst_name) or []
            for post in posts:
                # buscar id del post — _post_dict no lo incluye, asi que matcheo por url
                if post.get("tag_primary"):
                    continue  # ya tiene tag (top5 lo gano via ref)
                # buscar en tag_map por matching url o id en rows
                url = post.get("url") or ""
                # Plan B: search por url
                found = None
                for pid, (tags, primary) in tag_map.items():
                    # No tenemos id en _post_dict — usamos URL como bridge
                    if url and pid and pid in url:  # post id suele estar en URL
                        found = (tags, primary); break
                if found:
                    post["tags"]        = found[0]
                    post["tag_primary"] = found[1]
                    total_propagated += 1
                else:
                    # Fallback: asignar default si sigue sin tag
                    post["tags"]        = ["marca"]
                    post["tag_primary"] = "marca"
                    total_missing += 1
    print(f"  ✓ Propagados: {total_propagated} | Forzados a 'marca' (sin match): {total_missing}")



def build_data_dict(sb: Supabase, period: str = "diagnostico") -> dict:
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
    if period == "diagnostico":
        START = _dt(2026, 1, 1,  tzinfo=BG)
        END   = _dt(2026, 5, 31, 23, 59, 59, tzinfo=BG)
    else:
        y, m = period.split("-")
        import calendar as _cal
        yi, mi = int(y), int(m)
        START = _dt(yi, mi, 1, tzinfo=BG)
        END   = _dt(yi, mi, _cal.monthrange(yi, mi)[1], 23, 59, 59, tzinfo=BG)

    def _to_bg(s):
        if not s: return None
        try:
            t = _dt.fromisoformat(s.replace("Z", "+00:00")) if s.endswith("Z") else _dt.fromisoformat(s)
            if t.tzinfo is None: t = t.replace(tzinfo=_tz.utc)
            return t.astimezone(BG)
        except Exception:
            return None

    # --- accounts: preferir snapshot del periodo, fallback al de diagnostico ---
    accounts_rows = sb.select("accounts",
        filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.{period}")
    if not accounts_rows and period != "diagnostico":
        print(f"  Sin accounts para {period}, usando snapshot de diagnostico")
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
    # NOTA: posts table tiene tags persistidos en columnas tags/tag_primary/tagged_at
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
            # Preferir thumbnail local si existe (CDN URLs expiran)
            "media_url":  r.get("media_url_local") or r.get("media_url") or "",
            "ts":         ts,
            # Tags persistidos previamente (si los hay)
            "tags":         r.get("tags"),
            "tag_primary":  r.get("tag_primary"),
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
                "atipicos": [], "worst5": [], "outlier_threshold": 0,
                "outlier_rule": "engagement > 5x mediana del periodo",
            }
            continue

        engs = [p["engagement"] for p in ps]
        total_eng = sum(engs)
        prom = round(total_eng / n, 1)
        med = sorted(engs)[n // 2]

        # PRIMERO: identificar atipicos (engagement > 5x mediana, piso 5)
        med_floor = max(med, 5)
        outlier_threshold = med_floor * 5
        atipicos = sorted(
            [p for p in ps if p["engagement"] > outlier_threshold],
            key=lambda p: -p["engagement"]
        )
        atipicos_set = {p["id"] for p in atipicos}
        # POSTS TIPICOS: ps SIN atipicos → usados en TODOS los aggregates de gráficas
        ps_typical = [p for p in ps if p["id"] not in atipicos_set]
        cambio2_metricas_organicas.txt

        # by_type SOLO con tipicos
        type_counts = _Counter()
        type_engs   = _Counter()
        for p in ps_typical:
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

        # by_day (0=Lun) SOLO con tipicos
        day_counts = [0]*7
        day_engs   = [0]*7
        for p in ps_typical:
            d = p["ts"].weekday()
            day_counts[d] += 1
            day_engs[d]   += p["engagement"]
        by_day = {
            "labels": DOW,
            "counts": day_counts,
            "engagement_promedio": [round(day_engs[i]/day_counts[i], 1) if day_counts[i] else 0 for i in range(7)],
        }

        # by_hour (Bogota) SOLO con tipicos
        h_counts = _Counter()
        h_engs   = _Counter()
        for p in ps_typical:
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

        # by_week SOLO con tipicos
        week_counts = _Counter()
        week_engs   = _Counter()
        for p in ps_typical:
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

        # top_hashtags SOLO con tipicos
        hash_count = _Counter()
        for p in ps_typical:
            for tag in (p.get("hashtags") or []):
                if tag: hash_count[tag] += 1
        top_hashtags = hash_count.most_common(10)

        # captions_avg_len (sobre tipicos)
        captions_avg_len = round(sum(len(p["caption"] or "") for p in ps_typical) / n_typical, 1)

        # Top5 y worst5 sin duplicados (fix: en plataformas con pocos posts los mismos
        # aparecian en ambas tablas). Regla adaptativa:
        #   n <= 5:  solo top (los pocos que hay), NO hay peores separados
        #   6-10:    top 5 + peores = los que sobren (sin overlap)
        #   > 10:    top 5 + peores 5, garantizado sin overlap
        sorted_typical = sorted(ps_typical, key=lambda p: -p["engagement"])
        n_t = len(sorted_typical)
        if n_t <= 5:
            top5_normales = sorted_typical
            worst5 = []
        elif n_t <= 10:
            top5_normales = sorted_typical[:5]
            # los que sobran, ordenados de menor a mayor engagement (peores primero)
            remaining = [p for p in sorted_typical[5:] if p["engagement"] > 0]
            worst5 = sorted(remaining, key=lambda p: p["engagement"])
        else:
            top5_normales = sorted_typical[:5]
            remaining = [p for p in sorted_typical[5:] if p["engagement"] > 0]
            worst5 = sorted(remaining, key=lambda p: p["engagement"])[:5]

        def _post_dict(p):
            return {
                "url":         p["url"],
                "tipo":        p["type"],
                "fecha":       p["ts"].strftime("%Y-%m-%d"),
                "likes":       p["likes"],
                "caption":     p["caption"],
                "media_url":   p["media_url"],
                "engagement":  p["engagement"],
                "comentarios": p["comments"],
                "tags":        p.get("tags"),
                "tag_primary": p.get("tag_primary"),
            }

        top5 = [_post_dict(p) for p in top5_normales]
        atipicos_list = [_post_dict(p) for p in atipicos]
        worst5_list = [_post_dict(p) for p in worst5]

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
            "atipicos": atipicos_list,
            "worst5":   worst5_list,
            "outlier_threshold": outlier_threshold,
            "outlier_rule":      "engagement > 5x mediana del periodo",
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

    # Hook para tagging: pasarle al gemini_tag_posts_batched todos los posts del periodo
    all_for_tag = []
    for plat in ("instagram","facebook","tiktok","linkedin"):
        ps = [p for p in posts_bg if p["platform"] == plat]
        for i, p in enumerate(ps):
            all_for_tag.append({
                "key": (plat, p.get("id") or p.get("url") or f"{plat}-{i}"),
                "plat": plat,
                "tipo": p.get("type") or "post",
                "caption": (p.get("caption") or "")[:400],
                "ref": p,  # apuntara al dict del post; pero como ya construimos blocks con copias,
                            # esto no se va a propagar. Estrategia: tagging por (plat, post_id) y
                            # luego se reaplica al chart desde block["tag_summary"] precomputado.
            })
    return {
        "_all_posts_for_tagging": all_for_tag,
        "generated_at": _dt.now().strftime("%d/%m/%Y"),
        "ventana": {"desde": START.strftime("%Y-%m-%d"), "hasta": END.strftime("%Y-%m-%d")},
        "accounts": accounts,
        "consolidated": consolidated,
        "instagram": blocks["instagram"],
        "facebook":  blocks["facebook"],
        "tiktok":    blocks["tiktok"],
        "linkedin":  blocks["linkedin"],
        "fb_undated": 0,
        "fb_total":   blocks["facebook"].get("n_posts") or 0,
        "snapshots_history": snapshots,
        "periodo_label": PERIOD_LABEL if "PERIOD_LABEL" in globals() else "Diagnóstico (Ene-May 2026)",
        "periodo_id":    period,
    }


def _get_all_periods(sb) -> list[str]:
    """Lee los periodos disponibles en Supabase (tabla periods)."""
    rows = sb.select("periods", filter=f"client_id=eq.{CLIENT_ID}")
    ids = [r["id"] for r in rows]
    # Ordenar: diagnostico primero, luego meses ascendente
    def _key(pid):
        if pid == "diagnostico": return (0, "")
        return (1, pid)
    return sorted(ids, key=_key)


def _setup_period(period: str):
    """Configura globals para el periodo. Retorna (target_html, root_target o None)."""
    global PERIOD_LABEL, VENTANA_DESDE, VENTANA_HASTA, TARGET_DIR, TARGET_HTML, ROOT_TARGET
    if period == "diagnostico":
        VENTANA_DESDE = "2026-01-01"
        VENTANA_HASTA = "2026-05-31"
        PERIOD_LABEL  = "Diagnóstico (Ene-May 2026)"
        TARGET_DIR    = ROOT / "diagnostico"
        ROOT_TARGET   = ROOT / "index.html"
    else:
        y, m = period.split("-")
        yi, mi = int(y), int(m)
        VENTANA_DESDE = f"{yi:04d}-{mi:02d}-01"
        import calendar
        last_day = calendar.monthrange(yi, mi)[1]
        VENTANA_HASTA = f"{yi:04d}-{mi:02d}-{last_day:02d}"
        month_names = ["", "Enero","Febrero","Marzo","Abril","Mayo","Junio",
                       "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        PERIOD_LABEL  = f"{month_names[mi]} {yi}"
        TARGET_DIR    = ROOT / period
        ROOT_TARGET   = None
    TARGET_HTML = TARGET_DIR / "index.html"


def _build_one_period(sb, period: str) -> bool:
    """Builda UN periodo. Retorna True si escribio archivo."""
    _setup_period(period)
    print(f"\n═══ Construyendo periodo '{period}' → {TARGET_HTML.relative_to(ROOT)} ═══")
    try:
        data = build_data_dict(sb, period)
    except Exception as exc:
        print(f"  ✗ build_data_dict fallo: {exc}")
        return False

    # Enriquecimientos: aislados por función para que un fallo no cascada
    print("→ Enriqueciendo…")
    # 1) Heatmap + tagging + propagación
    try:
        posts = sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")
        # FIX 2026-07-16: filtrar posts al periodo antes de agregarlos al heatmap.
        # Sin esto, el heatmap de cualquier mes agrega TODOS los historicos del
        # cliente (ej: sandwich viral de enero salia en el heatmap de julio).
        if VENTANA_DESDE and VENTANA_HASTA:
            _start_iso = VENTANA_DESDE  # ej "2026-07-01"
            _end_iso   = VENTANA_HASTA  # ej "2026-07-31"
            _posts_periodo = []
            for _p in posts:
                _ts = _to_bogota(_parse_ts(_p.get("posted_at")))
                if not _ts:
                    continue
                _d = _ts.strftime("%Y-%m-%d")
                if _start_iso <= _d <= _end_iso:
                    _posts_periodo.append(_p)
            print(f"  posts filtrados al periodo [{_start_iso} -> {_end_iso}]: "
                  f"{len(_posts_periodo)}/{len(posts)}")
        else:
            _posts_periodo = posts
        enrich_by_day_hour_heatmap(data, _posts_periodo)
        all_for_tag = data.pop("_all_posts_for_tagging", [])
        data["__all_posts_for_tagging"] = all_for_tag
        import os
        gemini_tag_posts_batched(data, os.environ.get("GEMINI_API_KEY"), sb=sb, batch_size=25)
        data.pop("__all_posts_for_tagging", None)
        propagate_tags_to_data(data, sb)
    except Exception as exc:
        import traceback
        print(f"  ⚠ Enriquecimiento (tags+heatmap) fallo: {exc}")
        traceback.print_exc()

    # 2) Análisis por categorías (aislado)
    try:
        compute_category_analysis(data, sb)
    except Exception as exc:
        import traceback
        print(f"  ⚠ compute_category_analysis fallo: {exc}")
        traceback.print_exc()

    # 3) Deltas MoM (aislado, con fallback explícito a None)
    try:
        compute_deltas(data, sb, period)
    except Exception as exc:
        import traceback
        print(f"  ⚠ compute_deltas fallo: {exc}")
        traceback.print_exc()
        data["deltas"] = None

    # 4) Hallazgos + recomendaciones LLM del periodo (aislado)
    try:
        import os as _os_hz
        from pipeline.transform import hallazgos_llm as _hz
        _hz.generate(data, PERIOD_LABEL, _os_hz.environ.get("GEMINI_API_KEY"))
    except Exception as exc:
        import traceback
        print(f"  \u26a0 hallazgos_llm fallo: {exc}")
        traceback.print_exc()
        data["hallazgos_llm"] = None

    # Renderizar HTML clonando el template fuente
    src = SOURCE_HTML.read_text()
    data_json = json.dumps(data, ensure_ascii=False, separators=(", ", ": "))
    src = re.sub(r"const DATA = \{.*?\};", lambda m: f"const DATA = {data_json};", src, count=1, flags=re.DOTALL)
    # REPORT_META dinamico segun periodos disponibles
    all_periods = _get_all_periods(sb)
    def _label(pid):
        if pid == "diagnostico": return "Diagnóstico (Ene-May 2026)"
        y, m = pid.split("-")
        month_names = ["", "Enero","Febrero","Marzo","Abril","Mayo","Junio",
                       "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        return f"{month_names[int(m)]} {y}"
    new_meta = {
        "current": period,
        "available": [{"id": pid, "label": _label(pid), "url": f"/{pid}/" if pid != "diagnostico" else "/diagnostico/"}
                      for pid in all_periods],
    }
    meta_json = json.dumps(new_meta, ensure_ascii=False)
    src = re.sub(r"const REPORT_META = \{.*?\};", lambda m: f"const REPORT_META = {meta_json};", src, count=1, flags=re.DOTALL)

    # RESUMEN EJECUTIVO dinamico por periodo (reemplaza el hardcoded Ene-May)
    def _plat_line(plat_key, plat_cap):
        b = data.get(plat_key) or {}
        return {"n": b.get("n_posts") or 0, "et": b.get("engagement_total") or 0,
                "ep": b.get("engagement_promedio") or 0, "cap": plat_cap}
    plats = [_plat_line("instagram","Instagram"), _plat_line("facebook","Facebook"),
             _plat_line("tiktok","TikTok"),       _plat_line("linkedin","LinkedIn")]
    total_posts = sum(x["n"] for x in plats)
    total_eng   = sum(x["et"] for x in plats)
    top_vol = max(plats, key=lambda x: x["n"]) if total_posts > 0 else None
    top_eng = max(plats, key=lambda x: x["ep"]) if total_posts > 0 else None
    acc = data.get("accounts") or {}
    fb_audi = int((acc.get("Facebook") or {}).get("page_likes") or 0)
    ig_audi = int((acc.get("Instagram") or {}).get("seguidores") or 0)
    top_audi_plat, top_audi_val = ("Facebook", fb_audi) if fb_audi > ig_audi else ("Instagram", ig_audi)

    periodo_txt = "el periodo Ene–May 2026" if period == "diagnostico" else PERIOD_LABEL
    if total_posts > 0:
        low_cand = [x for x in plats if x["n"] > 0]
        low_vol = min(low_cand, key=lambda x: x["n"]) if low_cand else None
        partes = [
            f"<strong>En {periodo_txt}, Comapan publicó {total_posts} piezas en 4 redes "
            f"({total_eng:,} interacciones).</strong>",
            f"{top_eng['cap']} es el motor de eficiencia —mejor engagement por post "
            f"({round(top_eng['ep'])})—",
            f"{top_audi_plat} aporta el mayor alcance ({top_audi_val:,} de audiencia)",
        ]
        if low_vol and low_vol["cap"] != top_eng["cap"]:
            partes.append(f"y {low_vol['cap']} queda subutilizado ({low_vol['n']} "
                          f"post{'s' if low_vol['n'] != 1 else ''})")
        one = partes[0] + " " + ", ".join(partes[1:]) + f". Prioridad: sostener cadencia en {top_eng['cap']}."
    else:
        one = f"Sin actividad registrada en el período <strong>{periodo_txt}</strong> para las 4 redes analizadas."

    resumen_html = f'<p style="margin: 0; font-size: 15px; line-height: 1.7;">{one}</p>'
    # Reemplazar el bloque de 3 <p> hardcoded dentro de la caja .resumen-corp
    src = re.sub(
        r'(<div style="font-size: 14\.5px;[^"]*color: #2a2a2a;[^"]*">)(.*?)(</div>\s*</div>)',
        lambda m: m.group(1) + "\n      " + resumen_html + "\n    " + m.group(3),
        src, count=1, flags=re.DOTALL
    )

    # Eyebrow dinamico del panorama (reemplaza fecha fija segun periodo)
    panorama_label = "Ene a May 2026" if period == "diagnostico" else PERIOD_LABEL
    src = src.replace("Panorama general \u00b7 Ene a May 2026",
                      f"Panorama general \u00b7 {panorama_label}", 1)

    # Post-process (unificar fechas viejas, etc.)
    for old_s, new_s in [
        ("Feb a Abr 2026", "Ene a May 2026"),
        ("Feb-Abr 2026",   "Ene-May 2026"),
        ("feb a abr 2026", "ene a may 2026"),
        ("feb-abr 2026",   "ene-may 2026"),
        ("Feb-Abr",        "Ene-May"),
    ]:
        src = src.replace(old_s, new_s)
    src = src.replace(
        'kpi("Posts publicados", fmt(d.n_posts)',
        'kpi("Posts publicados", fmt(data.n_posts)'
    )

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_HTML.write_text(src)
    print(f"  ✓ Generado: {TARGET_HTML.relative_to(ROOT)} ({len(src):,} bytes)")
    if ROOT_TARGET is not None:
        ROOT_TARGET.write_text(src)
        print(f"  ✓ Sincronizado a landing: {ROOT_TARGET.relative_to(ROOT)}")
    return True


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="all",
                        help="ID del periodo o 'all' para regenerar todos los disponibles")
    args = parser.parse_args()

    sb = Supabase()

    if args.period == "all":
        periods = _get_all_periods(sb)
        print(f"═══ MODO ALL — {len(periods)} periodos detectados: {periods} ═══")
        results = {}
        for pid in periods:
            results[pid] = _build_one_period(sb, pid)
        ok = sum(1 for v in results.values() if v)
        print(f"\n═══ RESUMEN: {ok}/{len(periods)} periodos generados ═══")
        for pid, v in results.items():
            print(f"  {'✓' if v else '✗'} {pid}")
        return 0 if ok == len(periods) else 1

    # Modo single-period (compat con uso anterior)
    ok = _build_one_period(sb, args.period)
    return 0 if ok else 1

    # Heatmap (matriz dia x hora) + tagging de TODOS los posts via Gemini batched
    print("→ Generando heatmap dia x hora + tagging LLM (batched)…")


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
