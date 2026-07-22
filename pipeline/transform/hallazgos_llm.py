"""Genera hallazgos + recomendaciones del período con Gemini, a partir de la
data ya computada del build (KPIs, top posts, categorías, deltas, heatmap).

Produce data["hallazgos_llm"] con la forma EXACTA que consume el template:

    {
      "_meta": {"model": ..., "attempts": 1, "generated_at": "YYYY-MM-DD..."},
      "resumen_ejecutivo": "…",
      "hallazgos_top": [
        {
          "categoria": "patron|anomalia|tendencia|brecha|correlacion|punto_ciego",
          "plataforma": "instagram|facebook|tiktok|linkedin|cross",
          "dato": "…", "comparativo": "…", "interpretacion": "…", "implicacion": "…",
          "recomendacion": {"accion": "…", "prioridad": "alta|media|baja",
                            "esfuerzo": "alto|medio|bajo"}
        }, …
      ],
      "recomendaciones": [
        {"title": "…", "body": "…", "tags": ["Esfuerzo bajo", "Impacto alto", "30 días"]}, …
      ]
    }

Filosofía: si algo falla (sin API key, error de red, JSON inválido), se deja
data["hallazgos_llm"] = None. El template oculta la sección — NUNCA se muestran
datos inventados ni de otro período.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

CATEGORIAS_VALIDAS = {"patron", "anomalia", "tendencia", "brecha", "correlacion", "punto_ciego"}
PLATAFORMAS_VALIDAS = {"instagram", "facebook", "tiktok", "linkedin", "cross"}
PRIORIDADES = {"alta", "media", "baja"}
ESFUERZOS = {"alto", "medio", "bajo"}


def _digest_plataforma(block: dict) -> dict:
    """Resumen compacto de una plataforma para el prompt (pocos tokens)."""
    if not block or not block.get("n_posts"):
        return {}
    mejor_dia = None
    by_day = block.get("by_day") or {}
    if by_day.get("labels") and by_day.get("engagement_promedio"):
        pares = list(zip(by_day["labels"], by_day["engagement_promedio"]))
        if pares:
            mejor_dia = max(pares, key=lambda p: p[1] or 0)[0]
    mejor_hora = None
    by_hour = block.get("by_hour") or {}
    if by_hour.get("labels") and by_hour.get("engagement_promedio"):
        pares = list(zip(by_hour["labels"], by_hour["engagement_promedio"]))
        if pares:
            mejor_hora = max(pares, key=lambda p: p[1] or 0)[0]
    top = (block.get("top5") or [{}])[0]
    return {
        "n_posts": block.get("n_posts"),
        "engagement_total": block.get("engagement_total"),
        "engagement_promedio": block.get("engagement_promedio"),
        "engagement_mediana": block.get("engagement_mediana"),
        "mejor_dia": mejor_dia,
        "mejor_hora": mejor_hora,
        "mejor_post": {
            "fecha": top.get("fecha"),
            "engagement": top.get("engagement"),
            "categoria": top.get("tag_primary"),
            "caption": (top.get("caption") or "")[:160],
        },
        "categorias": block.get("tag_summary") or {},
    }


def _build_digest(data: dict, period_label: str) -> dict:
    plataformas = {}
    for plat in ("instagram", "facebook", "tiktok", "linkedin"):
        d = _digest_plataforma(data.get(plat) or {})
        if d:
            plataformas[plat] = d
    total_posts = sum(p.get("n_posts", 0) for p in plataformas.values())
    total_eng = sum((data.get(pl) or {}).get("engagement_total", 0) for pl in plataformas)
    ca = data.get("category_analysis") or {}
    return {
        "periodo": period_label,
        "totales": {"posts": total_posts, "engagement": total_eng},
        "plataformas": plataformas,
        "deltas_mom": data.get("deltas"),
        "mix_categorias": ca.get("mix_global"),
        "gaps_categorias": ca.get("gaps"),
    }


SYSTEM_PROMPT = """Eres un analista senior de social media marketing. Analizas el desempeño mensual de una marca (Comapan, panadería colombiana) en 4 redes: Instagram, Facebook, TikTok y LinkedIn.

Tu tarea: a partir de los datos REALES del período que te doy, generar hallazgos y recomendaciones ESPECÍFICOS Y ACCIONABLES. Nunca inventes números; usa solo los del input. Si un dato no está, no lo menciones.

Responde SOLO con un JSON válido (sin markdown, sin explicaciones) con esta forma EXACTA:

{
  "resumen_ejecutivo": "2-3 frases con la síntesis del mes, en español, mencionando cifras reales.",
  "hallazgos_top": [
    {
      "categoria": "patron|anomalia|tendencia|brecha|correlacion|punto_ciego",
      "plataforma": "instagram|facebook|tiktok|linkedin|cross",
      "dato": "El dato objetivo con su número real.",
      "comparativo": "Contra qué se compara (vs mes anterior, vs otras redes, vs promedio).",
      "interpretacion": "Qué significa en lenguaje claro.",
      "implicacion": "Por qué le importa a la marca.",
      "recomendacion": {"accion": "Acción concreta.", "prioridad": "alta|media|baja", "esfuerzo": "alto|medio|bajo"}
    }
  ],
  "recomendaciones": [
    {"title": "Título corto de la recomendación", "body": "1-2 frases explicando qué hacer y por qué, con base en los datos del mes.", "tags": ["Esfuerzo bajo|medio|alto", "Impacto bajo|medio|alto", "30 días|30-60 días|60-90 días"]}
  ]
}

Reglas:
- Entre 4 y 6 hallazgos en "hallazgos_top", ordenados de mayor a menor relevancia.
- Exactamente 3 recomendaciones priorizadas en "recomendaciones".
- Usa las categorías y valores enumerados TAL CUAL (minúsculas).
- Todo en español neutro-colombiano, tono profesional y directo.
- Las recomendaciones deben derivarse de los datos de ESTE mes, no ser genéricas."""


def generate(data: dict, period_label: str, api_key) -> None:
    """Genera data['hallazgos_llm']. En cualquier fallo, lo deja en None."""
    data["hallazgos_llm"] = None  # default seguro

    if not api_key:
        print("  ⚠ hallazgos_llm: sin GEMINI_API_KEY, sección se omite")
        return

    try:
        from pipeline.transform.llm_providers import gemini
    except Exception as exc:
        print(f"  ⚠ hallazgos_llm: no pude importar gemini: {exc}")
        return

    digest = _build_digest(data, period_label)
    user_prompt = "Datos del período:\n" + json.dumps(digest, ensure_ascii=False, indent=1)

    raw = None
    attempts = 0
    for attempt in range(1, 3):  # hasta 2 intentos
        attempts = attempt
        try:
            raw = gemini.call(SYSTEM_PROMPT, user_prompt, max_tokens=6000, temperature=0.3)
            break
        except Exception as exc:
            print(f"  ⚠ hallazgos_llm intento {attempt} falló: {exc}")
            raw = None

    if not raw:
        print("  ⚠ hallazgos_llm: sin respuesta de Gemini, sección se omite")
        return

    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.split("```", 2)[1] if "```" in txt[3:] else txt
        txt = txt.replace("json", "", 1).strip("` \n")
    try:
        parsed = json.loads(txt)
    except Exception as exc:
        print(f"  ⚠ hallazgos_llm: JSON inválido ({exc}), sección se omite")
        return

    hallazgos = parsed.get("hallazgos_top")
    if not isinstance(hallazgos, list) or not hallazgos:
        print("  ⚠ hallazgos_llm: sin hallazgos_top válidos, sección se omite")
        return

    clean_hallazgos = []
    for h in hallazgos:
        if not isinstance(h, dict):
            continue
        cat = str(h.get("categoria", "")).lower()
        plat = str(h.get("plataforma", "")).lower()
        reco = h.get("recomendacion") or {}
        prio = str(reco.get("prioridad", "")).lower()
        esf = str(reco.get("esfuerzo", "")).lower()
        clean_hallazgos.append({
            "categoria": cat if cat in CATEGORIAS_VALIDAS else "patron",
            "plataforma": plat if plat in PLATAFORMAS_VALIDAS else "cross",
            "dato": str(h.get("dato", "")),
            "comparativo": str(h.get("comparativo", "")),
            "interpretacion": str(h.get("interpretacion", "")),
            "implicacion": str(h.get("implicacion", "")),
            "recomendacion": {
                "accion": str(reco.get("accion", "")),
                "prioridad": prio if prio in PRIORIDADES else "media",
                "esfuerzo": esf if esf in ESFUERZOS else "medio",
            },
        })

    if not clean_hallazgos:
        print("  ⚠ hallazgos_llm: hallazgos vacíos tras validar, sección se omite")
        return

    recomendaciones = []
    for r in (parsed.get("recomendaciones") or [])[:3]:
        if not isinstance(r, dict):
            continue
        tags = r.get("tags")
        if not isinstance(tags, list):
            tags = []
        recomendaciones.append({
            "title": str(r.get("title", "")),
            "body": str(r.get("body", "")),
            "tags": [str(t) for t in tags][:3],
        })

    data["hallazgos_llm"] = {
        "_meta": {
            "model": "gemini-2.5-flash",
            "attempts": attempts,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "resumen_ejecutivo": str(parsed.get("resumen_ejecutivo", "")),
        "hallazgos_top": clean_hallazgos,
        "recomendaciones": recomendaciones,
    }
    print(f"  ✓ hallazgos_llm: {len(clean_hallazgos)} hallazgos + {len(recomendaciones)} recomendaciones generados")
