"""Tests del módulo render — validan que template + DATA → HTML correcto."""
from __future__ import annotations

from pipeline.render.build import render, _serialize_data


SAMPLE_DATA = {
    "generated_at": "16/06/2026",
    "ventana": {"desde": "2026-03-18", "hasta": "2026-06-16"},
    "accounts": {"Instagram": {"username": "test"}},
    "instagram": {"n_posts": 5, "engagement_total": 100},
}


def test_serializer_is_single_line():
    out = _serialize_data(SAMPLE_DATA)
    assert "\n" not in out
    assert out.startswith("{")
    assert out.endswith("}")
    # Caracteres no-ASCII se preservan (no escaping)
    data_with_emoji = {"k": "café ☕"}
    assert "café ☕" in _serialize_data(data_with_emoji)


def test_render_replaces_marker_with_data():
    template = (
        "<html><head></head><body>\n"
        "<script>\n"
        "/* DATA_INJECTION_MARKER — placeholder */\n"
        "function init(){console.log(DATA.generated_at);}\n"
        "</script>\n"
        "</body></html>\n"
    )
    out = render(template, SAMPLE_DATA)
    assert "DATA_INJECTION_MARKER" not in out
    assert 'const DATA = {"generated_at": "16/06/2026"' in out
    # El resto del template intacto
    assert "<html><head></head><body>" in out
    assert "function init()" in out


def test_render_only_replaces_first_marker():
    template = (
        "/* DATA_INJECTION_MARKER */\n"
        "/* DATA_INJECTION_MARKER aparece de nuevo en un comentario */\n"
    )
    out = render(template, SAMPLE_DATA)
    # El primero se reemplaza
    assert out.startswith("const DATA = {")
    # El segundo (segunda aparición) NO debe reemplazarse — queda como estaba
    assert "DATA_INJECTION_MARKER aparece de nuevo" in out


def test_render_fails_when_no_marker():
    template = "<html>sin marker</html>"
    try:
        render(template, SAMPLE_DATA)
    except RuntimeError as exc:
        assert "DATA_INJECTION_MARKER" in str(exc)
    else:
        raise AssertionError("Debía fallar sin marker")
