"""Notify: SMTP simple. Manda un correo de cierre con el resumen del run.

Usa la stdlib (smtplib + email.message) — no requiere paquetes extras.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from pipeline.util.log import get_logger

log = get_logger(__name__)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def build_subject(client_name: str, prefix: str, status: str) -> str:
    icon = {"ok": "✅", "warning": "⚠️", "error": "❌"}.get(status, "ℹ️")
    return f"{prefix} {icon} Reporte {client_name} — {status.upper()}"


def build_body_html(summary: dict[str, Any]) -> str:
    """Resume el run en HTML simple, sin frameworks."""
    platforms_html = "".join(
        f"<li><b>{p}</b>: {info.get('n_posts', '-')} posts · {info.get('status', '?')}</li>"
        for p, info in (summary.get("platforms") or {}).items()
    )
    return f"""<!doctype html>
<html><body style="font-family: sans-serif; max-width: 640px; margin: 24px;">
  <h2 style="color:#1F618D;">Reporte generado</h2>
  <p><b>Cliente:</b> {summary.get('client', '?')}<br>
     <b>Periodo:</b> {summary.get('period', '?')}<br>
     <b>Duración:</b> {summary.get('duration_seconds', '?')} s<br>
     <b>Commit:</b> <code>{summary.get('commit_sha', 'no_publish')}</code></p>
  <h3>Plataformas</h3>
  <ul>{platforms_html or '<li>(sin data)</li>'}</ul>
  <p><a href="{summary.get('url', '#')}">Ver reporte publicado</a></p>
  <hr>
  <p style="color:#888;font-size:12px;">Auto-enviado por Datalítica Pipeline.
     Si algo se ve mal, revisar el log del run en GitHub Actions.</p>
</body></html>"""


def send(
    summary: dict[str, Any],
    *,
    to: list[str],
    subject: str,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
) -> None:
    """Envía el correo. Si faltan credenciales SMTP, hace log y skip."""
    host = smtp_host or _env("SMTP_HOST", "smtp.gmail.com")
    port = smtp_port or int(_env("SMTP_PORT", "587"))
    user = smtp_user or _env("SMTP_USER")
    pwd = smtp_password or _env("SMTP_PASSWORD")

    if not (user and pwd and to):
        log.warning("notify_skipped_no_creds", extra={"reason": "SMTP creds o destinatarios faltantes"})
        return

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content("Tu cliente de correo no soporta HTML. Ver versión HTML.")
    msg.add_alternative(build_body_html(summary), subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, pwd)
            smtp.send_message(msg)
        log.info("notify_sent", extra={"to": to, "subject": subject})
    except Exception as exc:
        log.error("notify_failed", extra={"error": str(exc), "to": to})
