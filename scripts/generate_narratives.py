#!/usr/bin/env python3
"""Genera narrativas (resumen + headlines + chart insights) para un periodo,
usando los datos de Supabase + Gemini. Persiste en la tabla `summaries`.

Uso:
    python scripts/generate_narratives.py --period 2026-06
    python scripts/generate_narratives.py --period diagnostico

Env vars:
    SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.load.supabase_client import Supabase
from pipeline.transform.llm_providers.gemini import call as gemini_call
from pipeline.util.log import get_logger

log = get_logger("narratives")

CLIENT_ID = "comapan"

# IDs de gráficas que existen en el template
CHARTS_BY_PLATFORM = {
    "instagram": ["ig-week", "ig-type", "ig-dow", "ig-hour", "ig-top"],
    "facebook":  ["fb-type", "fb-week", "fb-dow", "fb-hour", "fb-top"],
    "tiktok":    ["tt-week", "tt-dow", "tt-top"],
    "linkedin":  ["li-week", "li-dow", "li-top"],
}
CHARTS_RANKING = ["posts-red", "eng-red", "eng-evolution"]
ALL_CHART_IDS = sum(CHARTS_BY_PLATFORM.values(), []) + CHARTS_RANKING

CHART_DESCRIPTIONS = {
    "ig-week": "Volumen semanal de publicación en Instagram",
    "ig-type": "Engagement promedio por tipo de contenido en Instagram",
    "ig-dow":  "Mejor día de la semana en Instagram",
    "ig-hour": "Distribución por hora del día en Instagram",
    "ig-top":  "Top 5 publicaciones de Instagram por engagement",
    "fb-type": "Engagement promedio por tipo de publicación en Facebook",
    "fb-week": "Volumen semanal en Facebook",
    "fb-dow":  "Mejor día de la semana en Facebook",
    "fb-hour": "Distribución por hora del día en Facebook",
    "fb-top":  "Top 5 publicaciones de Facebook por engagement",
    "tt-week": "Volumen semanal de videos en TikTok",
    "tt-dow":  "Mejor día de la semana en TikTok",
    "tt-top":  "Top 5 videos de TikTok por engagement",
    "li-week": "Volumen semanal en LinkedIn",
    "li-dow":  "Mejor día de la semana en LinkedIn",
    "li-top":  "Top 5 publicaciones de LinkedIn por engagement",
    "posts-red":      "Posts publicados por red social (comparativo)",
    "eng-red":        "Engagement total por red social (comparativo)",
    "eng-evolution":  "Evolución semanal del engagement por red",
}

SYSTEM = """Eres analista senior de Datalítica generando narrativas de un reporte mensual de redes sociales.

REGLAS INNEGOCIABLES:
1. Estilo storytelling — como si le explicaras a un gerente ocupado, NO un dump de números.
2. Cada "hallazgo" en chart_insights DEBE contener al menos un número con contexto.
3. Cada "accion" es una sola acción concreta para el próximo mes.
4. Cada "headline" por plataforma cuenta una historia en 1-2 oraciones, con números clave.
5. El resumen ejecutivo es lo que un gerente leería en 30 segundos: ≤120 palabras, top-down, qué pasó y qué hacer.
6. PROHIBIDO usar adjetivos vacíos: genial, importante, destacado, significativo, bueno, sobresaliente, excelente.
7. Distingue correlación de causalidad.
8. Si una plataforma no tiene posts en el periodo (n_posts=0), las gráficas de esa red son "punto ciego" — di literalmente "Sin actividad este periodo, no hay datos para analizar" y propon una acción de baseline.
9. OUTPUT: JSON puro, sin markdown, sin texto adicional, exactamente con el schema indicado.
"""


def fetch_period_data(sb: Supabase, period_id: str) -> dict:
    """Construye un resumen compacto del periodo para el prompt."""
    period = sb.select("periods", filter=f"id=eq.{period_id}")[0]
    accounts = sb.select("accounts", filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.{period_id}")
    aggs = sb.select("aggregates", filter=f"client_id=eq.{CLIENT_ID}&period_id=eq.{period_id}")

    by_plat: dict = {}
    for plat in ("instagram","facebook","tiktok","linkedin"):
        by_plat[plat] = {
            "account": next((a for a in accounts if a["platform"] == plat), {}),
            "metrics": {a["metric_name"]: a["metric_value"]
                        for a in aggs if a["platform"] == plat}
        }

    return {
        "period": {
            "id": period["id"],
            "label": period["label"],
            "starts_on": period["starts_on"],
            "ends_on": period["ends_on"],
        },
        "platforms": by_plat,
    }


def build_user_prompt(period_data: dict) -> str:
    p = period_data["period"]

    # Resumir cada plataforma compactamente
    plat_summary = {}
    for plat, info in period_data["platforms"].items():
        acc = info["account"]
        m = info["metrics"]
        plat_summary[plat] = {
            "username":      acc.get("username"),
            "followers":     acc.get("followers"),
            "page_likes":    acc.get("page_likes"),
            "n_posts":       m.get("n_posts", (m.get("engagement_stats") or {}).get("n_posts", 0)),
            "engagement_total":     m.get("engagement_total", (m.get("engagement_stats") or {}).get("engagement_total", 0)),
            "engagement_promedio":  m.get("engagement_promedio", (m.get("engagement_stats") or {}).get("engagement_promedio", 0)),
            "by_type":       m.get("by_type"),
            "by_day":        m.get("by_day"),
            "by_hour":       m.get("by_hour"),
            "by_week":       m.get("by_week"),
            "top_hashtags":  m.get("top_hashtags"),
            "top5_engagements": [t.get("engagement") for t in (m.get("top5") or [])],
        }

    chart_keys_str = ", ".join(f'"{c}"' for c in ALL_CHART_IDS)

    return f"""CLIENTE: Comapan (Catorce Días Colombia)
PERIODO: {p['label']} ({p['starts_on']} a {p['ends_on']})

DATOS DEL PERIODO (resumen compacto):
{json.dumps(plat_summary, ensure_ascii=False, indent=2)}

GENERA un JSON con EXACTAMENTE este schema:
{{
  "resumen_ejecutivo": "string ≤120 palabras, storytelling top-down",
  "headlines": {{
    "instagram": "string ≤2 oraciones",
    "facebook":  "string ≤2 oraciones",
    "tiktok":    "string ≤2 oraciones",
    "linkedin":  "string ≤2 oraciones"
  }},
  "chart_insights": {{
    {chart_keys_str.replace('"', chr(34))}: cada uno como {{"hallazgo": "string con número", "accion": "string ≤20 palabras"}}
  }}
}}

Charts y qué muestran:
{json.dumps(CHART_DESCRIPTIONS, ensure_ascii=False, indent=2)}

Responde SOLO JSON puro. Nada antes, nada después.
"""


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-z]*\n?|\n?```$", "", t, flags=re.IGNORECASE).strip()
    return t


def validate(obj: dict) -> list[str]:
    errors = []
    if not isinstance(obj.get("resumen_ejecutivo"), str) or not obj["resumen_ejecutivo"].strip():
        errors.append("resumen_ejecutivo vacío")
    headlines = obj.get("headlines") or {}
    for plat in ("instagram","facebook","tiktok","linkedin"):
        if not isinstance(headlines.get(plat), str) or not headlines[plat].strip():
            errors.append(f"headline.{plat} vacío")
    ci = obj.get("chart_insights") or {}
    for chart_id in ALL_CHART_IDS:
        v = ci.get(chart_id)
        if not isinstance(v, dict):
            errors.append(f"chart_insight.{chart_id} no es dict")
            continue
        if not v.get("hallazgo"):
            errors.append(f"chart_insight.{chart_id}.hallazgo vacío")
    return errors


def upsert_narrative(sb: Supabase, period_id: str, obj: dict, model: str) -> None:
    row = {
        "client_id": CLIENT_ID,
        "period_id": period_id,
        "resumen": obj["resumen_ejecutivo"],
        "headlines": obj["headlines"],
        "chart_insights": obj["chart_insights"],
        "generated_by": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    sb.upsert("summaries", [row], on_conflict="client_id,period_id")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", required=True, help="ID del periodo (ej 2026-06)")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()

    sb = Supabase()
    period_data = fetch_period_data(sb, args.period)
    user_prompt = build_user_prompt(period_data)
    log.info("narrative_gen_start", extra={"period": args.period, "model": args.model})

    last_errs: list[str] = []
    for attempt in range(1, args.max_attempts + 1):
        try:
            txt = gemini_call(SYSTEM, user_prompt, model=args.model, max_tokens=12000, temperature=0.0)
            obj = json.loads(_strip_fence(txt))
            errs = validate(obj)
            if not errs:
                upsert_narrative(sb, args.period, obj, args.model)
                log.info("narrative_gen_ok", extra={"period": args.period, "attempt": attempt})
                print(f"\n✅ Narrativa generada y guardada en summaries para {args.period}")
                print(f"   Resumen ejecutivo: {obj['resumen_ejecutivo'][:120]}...")
                print(f"   Headlines: {len(obj['headlines'])} plataformas")
                print(f"   Chart insights: {len(obj['chart_insights'])} gráficas")
                return 0
            last_errs = errs
            log.warning("narrative_validation_failed", extra={"attempt": attempt, "errors": errs[:5]})
        except Exception as exc:
            last_errs = [str(exc)]
            log.error("narrative_gen_error", extra={"attempt": attempt, "error": str(exc)})

    print(f"\n❌ Falló tras {args.max_attempts} intentos: {last_errs[:3]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
