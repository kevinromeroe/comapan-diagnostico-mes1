"""Tests del módulo render — validan que template + DATA → HTML correcto.

Refactor iter 4.5: ahora _serialize en lugar de _serialize_data, y render()
recibe (template, data, report_meta) en vez de (template, data).
"""
from __future__ import annotations

from pipeline.render.build import _serialize, render


SAMPLE_DATA = {
    "generated_at": "16/06/2026",
    "ventana": {"desde": "2026-03-18", "hasta": "2026-06-16"},
    "accounts": {"Instagram": {"username": "test"}},
    "instagram": {"n_posts": 5, "engagement_total": 100},
}

SAMPLE_META = {
    "current": "2026-06",
    "available": [
        {"id": "diagnostico", "label": "Diagnóstico", "url": "/diagnostico/"},
        {"id": "2026-06", "label": "Junio 2026", "url": "/2026-06/"},
    ],
}


def test_serializer_is_single_line():
    out = _serialize(SAMPLE_DATA)
    assert "\n" not in out
    assert out.startswith("{")
    assert out.endswith("}")
    # Caracteres no-ASCII se preservan (no escaping)
    data_with_emoji = {"k": "café ☕"}
    assert "café ☕" in _serialize(data_with_emoji)


def test_render_replaces_data_marker():
    template = (
        "<html><head></head><body>\n"
        "<script>\n"
        "/* DATA_INJECTION_MARKER — placeholder */\n"
        "function init(){console.log(DATA.generated_at);}\n"
        "</script>\n"
        "/* PERIODS_INJECTION_MARKER — placeholder */\n"
        "</body></html>\n"
    )
    out = render(template, SAMPLE_DATA, SAMPLE_META)
    assert "DATA_INJECTION_MARKER" not in out
    assert "PERIODS_INJECTION_MARKER" not in out
    assert 'const DATA = {"generated_at": "16/06/2026"' in out
    assert 'const REPORT_META = {"current": "2026-06"' in out
    # El resto del template intacto
    assert "<html><head></head><body>" in out
    assert "function init()" in out


def test_render_only_replaces_first_data_marker():
    template = (
        "/* DATA_INJECTION_MARKER */\n"
        "/* PERIODS_INJECTION_MARKER */\n"
        "/* DATA_INJECTION_MARKER aparece de nuevo en un comentario */\n"
    )
    out = render(template, SAMPLE_DATA, SAMPLE_META)
    # El primero del DATA se reemplaza por const DATA
    assert out.startswith("const DATA = {")
    # El segundo (en línea distinta) NO debe reemplazarse — queda como estaba
    assert "DATA_INJECTION_MARKER aparece de nuevo" in out


def test_render_fails_when_no_data_marker():
    template = "<html>sin marker DATA pero con /* PERIODS_INJECTION_MARKER */</html>"
    try:
        render(template, SAMPLE_DATA, SAMPLE_META)
    except RuntimeError as exc:
        assert "DATA_INJECTION_MARKER" in str(exc)
    else:
        raise AssertionError("Debía fallar sin marker de DATA")
