"""Tests del módulo de insights LLM — schema + validación + rechazo."""
from __future__ import annotations

from pipeline.transform.insights_llm import (
    _parse_and_validate, _validate_hallazgo, generate_insights,
)


VALID_HALLAZGO = {
    "categoria": "patron",
    "plataforma": "instagram",
    "dato": "Los Reels generaron 132 interacciones promedio por post en mayo (n=51)",
    "comparativo": "3.7x más que los carruseles del mismo periodo (36 interacciones)",
    "interpretacion": "Reels concentran el engagement y desplazan a otros formatos.",
    "implicacion": "Si se reduce inversión en Reels, cae el engagement global de IG.",
    "recomendacion": {
        "accion": "Mantener 70% del calendario en Reels y reducir carruseles a 1/semana",
        "prioridad": "alta",
        "esfuerzo": "bajo",
    },
}


def test_valid_hallazgo_passes():
    errors = _validate_hallazgo(VALID_HALLAZGO)
    assert errors == [], f"esperaba sin errores, vino: {errors}"


def test_rejects_hallazgo_without_number():
    bad = dict(VALID_HALLAZGO)
    bad["dato"] = "Los Reels son los que más interacciones generan en general"
    errors = _validate_hallazgo(bad)
    assert any("no contiene ningún número" in e for e in errors)


def test_rejects_forbidden_adjectives():
    for word in ["genial", "importante", "destacado", "significativo"]:
        bad = dict(VALID_HALLAZGO)
        bad["interpretacion"] = f"Es {word} para la marca tener este resultado."
        errors = _validate_hallazgo(bad)
        assert any("adjetivo vacío" in e for e in errors), \
            f"esperaba rechazo por '{word}', vinieron: {errors}"


def test_rejects_bad_categoria():
    bad = dict(VALID_HALLAZGO)
    bad["categoria"] = "interesante"
    errors = _validate_hallazgo(bad)
    assert any("categoria" in e for e in errors)


def test_rejects_missing_recomendacion():
    bad = dict(VALID_HALLAZGO)
    bad["recomendacion"] = {"accion": "...", "prioridad": "tal_vez", "esfuerzo": "bajo"}
    errors = _validate_hallazgo(bad)
    assert any("prioridad" in e for e in errors)


def test_parse_strips_markdown_fence():
    raw = '```json\n{"hallazgos_top": [], "resumen_ejecutivo": ""}\n```'
    parsed, errors = _parse_and_validate(raw)
    assert parsed is not None
    # vacío genera errors pero no JSON inválido
    assert not any("JSON inválido" in e for e in errors)


def test_parse_fails_on_invalid_json():
    parsed, errors = _parse_and_validate("esto no es json")
    assert parsed is None
    assert any("JSON inválido" in e for e in errors)


def test_generate_insights_skipped_no_api_key(monkeypatch=None):
    """Sin ANTHROPIC_API_KEY → retorna fallback graceful."""
    import os
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        out = generate_insights({"ventana": {"desde": "x", "hasta": "y"}}, skip_on_missing_key=True)
        assert out["hallazgos_top"] == []
        assert out["_meta"]["status"] == "skipped_no_api_key"
    finally:
        if saved:
            os.environ["ANTHROPIC_API_KEY"] = saved
