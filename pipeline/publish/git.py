"""Publish: commit + push del index.html y assets/thumbs/ al repo público.

Diseñado para funcionar en dos escenarios:
1. **CI (GitHub Actions)**: el workflow ya hizo checkout y configuró credenciales.
   Aquí solo necesitamos add + commit + push.
2. **Local**: el dev tiene el remote configurado (https con PAT o ssh).
   Mismo flujo.

Si no hay cambios reales, retorna sin commitear (no-op friendly).
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import date
from pathlib import Path

from pipeline.util.config import PROJECT_ROOT
from pipeline.util.log import get_logger

log = get_logger(__name__)


class PublishError(RuntimeError):
    pass


def _git(*args: str, cwd: Path = PROJECT_ROOT, check: bool = True) -> subprocess.CompletedProcess:
    """Ejecuta git con captura de salida y propagación clara de errores."""
    if shutil.which("git") is None:
        raise PublishError("git no está instalado en el entorno.")
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise PublishError(
            f"git {' '.join(args)} falló (rc={result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def has_changes(paths: list[str]) -> bool:
    """Devuelve True si alguno de los paths tiene diff vs HEAD."""
    res = _git("status", "--porcelain", "--", *paths, check=False)
    return bool(res.stdout.strip())


def ensure_identity(user_name: str, user_email: str) -> None:
    _git("config", "user.name", user_name)
    _git("config", "user.email", user_email)


def commit_and_push(
    paths: list[str],
    *,
    message: str,
    user_name: str = "Datalitica Bot",
    user_email: str = "bot@datalitica.com.co",
    branch: str = "main",
    max_pull_rebase_attempts: int = 2,
) -> bool:
    """
    Add + commit + push de los paths indicados. Si push falla por conflicto
    (refspec rejected — non-fast-forward), hace pull --rebase y reintenta.

    Returns: True si hubo commit/push, False si no había cambios.
    """
    if not has_changes(paths):
        log.info("publish_no_changes", extra={"paths": paths})
        return False

    ensure_identity(user_name, user_email)
    _git("add", "--", *paths)
    _git("commit", "-m", message)

    for attempt in range(1, max_pull_rebase_attempts + 1):
        push = _git("push", "origin", branch, check=False)
        if push.returncode == 0:
            log.info("publish_pushed", extra={"branch": branch, "attempt": attempt})
            return True
        stderr = (push.stderr or "").lower()
        if "non-fast-forward" in stderr or "rejected" in stderr or "fetch first" in stderr:
            log.warning(
                "publish_push_conflict_retry",
                extra={"attempt": attempt, "stderr": push.stderr.strip()},
            )
            _git("pull", "--rebase", "origin", branch)
            continue
        # Cualquier otro error: propagar
        raise PublishError(f"git push falló: {push.stderr.strip()}")
    raise PublishError("git push falló tras reintentos con pull --rebase.")


def commit_report(snapshot: date, period_id: str, *, cycle: str = "mensual") -> bool:
    """Helper para el caso común: publica index.html raíz + diagnostico/ +
    <period_id>/ + assets/thumbs/. El .gitignore se encarga de blindar data/."""
    msg = f"Reporte {cycle} {snapshot.isoformat()} — auto-generado"
    paths = [
        "index.html",         # raíz (siempre se actualiza al último periodo)
        "diagnostico/",       # baseline congelado (re-rendido pero contenido idéntico)
        f"{period_id}/",      # subdir del periodo nuevo (ej: 2026-06/)
        "assets/thumbs/",     # nuevas miniaturas de top posts
    ]
    return commit_and_push(paths, message=msg)


def commit_all_deploy_artifacts(snapshot: date, *, cycle: str = "mensual",
                                 message: str | None = None) -> bool:
    """Alternativa robusta: `git add -A` desde la raíz y commit. Respeta el
    .gitignore (que blinda data/, secrets, raw, etc). Útil si en algún
    momento agregamos más subrutas y no queremos tocar este código."""
    ensure_identity("Datalitica Bot", "bot@datalitica.com.co")
    _git("add", "-A")
    res = _git("status", "--porcelain", check=False)
    if not res.stdout.strip():
        log.info("publish_no_changes_global")
        return False
    msg = message or f"Reporte {cycle} {snapshot.isoformat()} — auto-generado"
    _git("commit", "-m", msg)
    for attempt in range(1, 3):
        push = _git("push", "origin", "main", check=False)
        if push.returncode == 0:
            log.info("publish_pushed_global", extra={"attempt": attempt})
            return True
        if "non-fast-forward" in (push.stderr or "").lower() or "rejected" in (push.stderr or "").lower():
            _git("pull", "--rebase", "origin", "main")
            continue
        raise PublishError(f"git push failed: {push.stderr.strip()}")
    raise PublishError("git push falló tras reintentos.")
