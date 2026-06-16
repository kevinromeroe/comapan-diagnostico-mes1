"""Tests del módulo notify — build_subject + build_body_html."""
from __future__ import annotations

from pipeline.notify.email import build_body_html, build_subject


def test_build_subject_ok_status():
    s = build_subject("Comapan", "[Datalitica]", "ok")
    assert "[Datalitica]" in s
    assert "Comapan" in s
    assert "OK" in s
    assert "✅" in s


def test_build_subject_error_status():
    s = build_subject("Comapan", "[Datalitica]", "error")
    assert "ERROR" in s
    assert "❌" in s


def test_body_html_renders_platform_summary():
    summary = {
        "client": "Comapan",
        "period": "2026-06-15",
        "duration_seconds": 124,
        "commit_sha": "abc123",
        "url": "https://comapan.datalitica.com.co",
        "platforms": {
            "instagram": {"status": "ok", "n_posts": 33},
            "linkedin": {"status": "warning", "n_posts": 0},
        },
    }
    html = build_body_html(summary)
    assert "Comapan" in html
    assert "2026-06-15" in html
    assert "instagram" in html
    assert "33 posts" in html
    assert "warning" in html
    assert "https://comapan.datalitica.com.co" in html


def test_body_html_handles_no_platforms():
    summary = {"client": "x", "period": "y", "duration_seconds": 0, "commit_sha": "", "url": "#"}
    html = build_body_html(summary)
    assert "(sin data)" in html
