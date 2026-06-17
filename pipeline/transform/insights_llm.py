"""Insights LLM — genera hallazgos automáticos llamando a Claude API.

Aplica el framework de docs/INSIGHTS_FRAMEWORK.md:
- 6 categorías de hallazgo: patron | anomalia | tendencia | brecha | correlacion | punto_ciego
- 5 elementos obligatorios por hallazgo (dato, comparativo, interpretacion, implicacion, recomendacion)
- Schema JSON validado a la fuerza
- Reintentos con prompt cada vez más estricto si la validación falla
- Fallback graceful: si no hay API key o falla 3 veces, retorna vacío con log

El output se integra al DATA canónico bajo `data["hallazgos_llm"]` y el template lo
renderiza condicionalmente (solo si hay hallazgos válidos).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from pipeline.util.log import get_logger

log = get_logger(__name__)

# Categorías y enums permitidos
CATEGORIAS = {"patron", "anomalia", "tendencia", "brecha", "correlacion", "punto_ciego"}
PLATAFORMAS = {"instagram", "facebook", "tiktok", "linkedin", "cross"}
PRIORIDADES = {"alta", "media", "baja"}
ESFUERZOS = {"alto", "medio", "bajo"}

# Palabras prohibidas — adjetivos vacíos sin sustento numérico
FORBIDDEN_WORDS_REGEX = re.compile(
    r"\b(genial|importante|destacad[oa]|significativ[oa]|bueno|interesante|excelente|"
    r"sobresaliente|maravillos[oa]|asombros[oa])\b",
    flags=re.IGNORECASE,
)

# Verifica que un campo "dato" contiene al menos un número
HAS_NUMBER = re.compile(r"\d")


# =============================================================
# Prompt — embebe el framework en el system message
# =============================================================
SYSTEM_PROMPT = """Eres un analista senior de datos de Datalítica Colombia.
Tu tarea es generar hallazgos analíticos sobre el desempeño de redes sociales
siguiendo un framework estricto, sin excepciones.

REGLAS INNEGOCIABLES:
1. Cada hallazgo DEBE contener un número concreto en el campo "dato".
   Sin número → hallazgo rechazado.
2. Cada hallazgo DEBE incluir un contraste explícito en el campo "comparativo"
   (vs periodo anterior, vs media histórica, vs otra plataforma, etc.).
3. PROHIBIDO usar adjetivos vacíos: "genial", "importante", "destacado",
   "significativo", "bueno", "interesante", "excelente", "sobresaliente".
   Si los usas, el output se rechaza.
4. Distingue correlación de causalidad. NO digas "es causado por"; di
   "coincide con", "se observa junto a".
5. Cambios <5% son ruido, no hallazgo. Cambios >15% son siempre hallazgo.
6. Cada recomendación DEBE tener prioridad (alta/media/baja) y esfuerzo
   (alto/medio/bajo). Sin priorización → rechazado.
7. Máximo 5 hallazgos top — el modelo NO debe devolver más.
8. Cada hallazgo se clasifica en UNA de estas categorías:
   - patron (comportamiento recurrente)
   - anomalia (outlier que requiere explicación)
   - tendencia (dirección sostenida ≥3 periodos)
   - brecha (gap entre realidad y potencial)
   - correlacion (relación entre variables, no causa)
   - punto_ciego (métrica relevante no medida)
9. Resumen ejecutivo: máx 200 palabras, top-down.

FORMATO DE OUTPUT — JSON ESTRICTO. NO incluyas texto fuera del JSON.
NO uses ```json``` ni markdown. Solo el JSON puro.
"""

OUTPUT_SCHEMA_DOC = """
{
  "hallazgos_top": [
    {
      "categoria": "patron | anomalia | tendencia | brecha | correlacion | punto_ciego",
      "plataforma": "instagram | facebook | tiktok | linkedin | cross",
      "dato": "string con número específico + unidad + contexto temporal",
      "comparativo": "string indicando contra qué se mide",
      "interpretacion": "máx 30 palabras: qué significa para el negocio",
      "implicacion": "máx 30 palabras: qué consecuencia tiene si no se atiende",
      "recomendacion": {
        "accion": "máx 25 palabras: acción concreta",
        "prioridad": "alta | media | baja",
        "esfuerzo": "alto | medio | bajo"
      }
    }
  ],
  "resumen_ejecutivo": "string ≤ 200 palabras"
}
"""


def _build_prompt(data: dict[str, Any], attempt: int) -> str:
    """Construye el user prompt. Más estricto en reintentos sucesivos."""
    extra_strictness = ""
    if attempt > 1:
        extra_strictness = (
            "\n\n⚠️ INTENTO " + str(attempt) + ": el intento anterior falló la validación. "
            "Revisa especialmente que CADA 'dato' tenga un número y que NO uses "
            "adjetivos vacíos. Devuelve SOLO el JSON puro, sin texto adicional."
        )

    # Pasamos un resumen compacto del DATA — no necesitamos las 100 líneas completas
    compact_data = {
        "ventana": data.get("ventana"),
        "accounts": {
            k: {
                "username": v.get("username"),
                "seguidores": v.get("seguidores"),
            }
            for k, v in (data.get("accounts") or {}).items()
        },
        "instagram": _platform_summary(data.get("instagram", {})),
        "facebook":  _platform_summary(data.get("facebook", {})),
        "tiktok":    _platform_summary(data.get("tiktok", {})),
        "linkedin":  _platform_summary(data.get("linkedin", {})),
    }

    return f"""Periodo analizado: {data.get('ventana', {}).get('desde')} a {data.get('ventana', {}).get('hasta')}

Genera EXACTAMENTE 5 hallazgos top + resumen ejecutivo siguiendo el schema:
{OUTPUT_SCHEMA_DOC}

DATA del periodo (resumen compacto):
{json.dumps(compact_data, ensure_ascii=False, indent=2)}
{extra_strictness}

Recuerda: SOLO JSON puro, sin markdown ni texto adicional.
"""


def _platform_summary(p: dict[str, Any]) -> dict[str, Any]:
    """Compacta el bloque de una plataforma para no inundar el prompt."""
    return {
        "n_posts": p.get("n_posts"),
        "engagement_total": p.get("engagement_total"),
        "engagement_promedio": p.get("engagement_promedio"),
        "engagement_mediana": p.get("engagement_mediana"),
        "by_type": p.get("by_type"),
        "by_day": p.get("by_day"),
        "top_hashtags": p.get("top_hashtags"),
        "captions_avg_len": p.get("captions_avg_len"),
        # Top5 solo con métricas (no captions ni URLs — el LLM no las necesita)
        "top5_engagements": [t.get("engagement") for t in (p.get("top5") or [])],
    }


# =============================================================
# Llamada a Claude
# =============================================================
def _call_claude(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4000,
    temperature: float = 0.0,
) -> str:
    """Llama a Claude API, retorna el texto crudo. Lazy import del SDK."""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("Paquete 'anthropic' no instalado. pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no definido en env vars.")

    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # message.content es una lista de bloques; el primero es texto
    return msg.content[0].text


# =============================================================
# Validación de schema y reglas
# =============================================================
def _validate_hallazgo(h: dict[str, Any]) -> list[str]:
    """Retorna lista de errores. Vacía = válido."""
    errors: list[str] = []

    # Campos obligatorios
    required = {"categoria", "plataforma", "dato", "comparativo",
                "interpretacion", "implicacion", "recomendacion"}
    missing = required - set(h.keys())
    if missing:
        errors.append(f"campos faltantes: {sorted(missing)}")
        return errors

    if h["categoria"] not in CATEGORIAS:
        errors.append(f"categoria '{h['categoria']}' no es válida")
    if h["plataforma"] not in PLATAFORMAS:
        errors.append(f"plataforma '{h['plataforma']}' no es válida")

    for field in ("dato", "comparativo", "interpretacion", "implicacion"):
        val = h.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"campo '{field}' vacío o no string")

    # Regla clave: el dato debe contener un número
    if isinstance(h.get("dato"), str) and not HAS_NUMBER.search(h["dato"]):
        errors.append("campo 'dato' no contiene ningún número")

    # Adjetivos vacíos
    for field in ("dato", "comparativo", "interpretacion", "implicacion"):
        val = h.get(field, "")
        if isinstance(val, str) and FORBIDDEN_WORDS_REGEX.search(val):
            m = FORBIDDEN_WORDS_REGEX.search(val)
            errors.append(f"campo '{field}' contiene adjetivo vacío: '{m.group()}'")

    # Recomendación
    reco = h.get("recomendacion") or {}
    if not isinstance(reco, dict):
        errors.append("recomendacion no es un dict")
    else:
        if not (isinstance(reco.get("accion"), str) and reco["accion"].strip()):
            errors.append("recomendacion.accion vacía")
        if reco.get("prioridad") not in PRIORIDADES:
            errors.append(f"prioridad '{reco.get('prioridad')}' no es válida")
        if reco.get("esfuerzo") not in ESFUERZOS:
            errors.append(f"esfuerzo '{reco.get('esfuerzo')}' no es válido")

    return errors


def _parse_and_validate(response_text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Parsea el JSON y valida. Retorna (output, errors)."""
    # Limpiar si el modelo coló accidentalmente ```json ... ```
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text, flags=re.IGNORECASE).strip()

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"JSON inválido: {exc}"]

    errors: list[str] = []
    hallazgos = obj.get("hallazgos_top")
    if not isinstance(hallazgos, list):
        errors.append("hallazgos_top no es lista")
        return None, errors
    if len(hallazgos) == 0:
        errors.append("hallazgos_top vacío")
    if len(hallazgos) > 5:
        errors.append(f"hallazgos_top tiene {len(hallazgos)} elementos, máximo 5")

    for i, h in enumerate(hallazgos):
        h_errors = _validate_hallazgo(h)
        for e in h_errors:
            errors.append(f"hallazgo[{i}]: {e}")

    resumen = obj.get("resumen_ejecutivo")
    if not isinstance(resumen, str) or not resumen.strip():
        errors.append("resumen_ejecutivo vacío")

    return obj, errors


# =============================================================
# Entry point
# =============================================================
def generate_insights(
    data: dict[str, Any],
    *,
    model: str = "claude-sonnet-4-6",
    max_attempts: int = 3,
    skip_on_missing_key: bool = True,
) -> dict[str, Any]:
    """
    Genera hallazgos LLM y los retorna en formato listo para inyectar al DATA.

    Returns:
        {
          "hallazgos_top": [...],          # vacía si falló
          "resumen_ejecutivo": "...",
          "_meta": {model, attempts, status, generated_at, error}
        }
    """
    meta: dict[str, Any] = {
        "model": model,
        "attempts": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    fallback = {"hallazgos_top": [], "resumen_ejecutivo": "", "_meta": meta}

    if not os.environ.get("ANTHROPIC_API_KEY"):
        meta["status"] = "skipped_no_api_key"
        if skip_on_missing_key:
            log.warning("insights_skipped_no_api_key")
            return fallback
        else:
            raise RuntimeError("ANTHROPIC_API_KEY no definido")

    last_errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        meta["attempts"] = attempt
        try:
            user_prompt = _build_prompt(data, attempt)
            response = _call_claude(SYSTEM_PROMPT, user_prompt, model=model)
            parsed, errors = _parse_and_validate(response)
            if not errors and parsed:
                meta["status"] = "ok"
                log.info("insights_generated", extra={"attempt": attempt, "n_hallazgos": len(parsed["hallazgos_top"])})
                return {
                    "hallazgos_top": parsed["hallazgos_top"],
                    "resumen_ejecutivo": parsed["resumen_ejecutivo"],
                    "_meta": meta,
                }
            last_errors = errors
            log.warning("insights_validation_failed", extra={"attempt": attempt, "errors": errors[:5]})
        except Exception as exc:
            last_errors = [str(exc)]
            log.error("insights_call_failed", extra={"attempt": attempt, "error": str(exc)})

    meta["status"] = "failed_validation"
    meta["error"] = last_errors[:5]
    log.error("insights_giving_up", extra={"errors": last_errors[:5]})
    fallback["_meta"] = meta
    return fallback
