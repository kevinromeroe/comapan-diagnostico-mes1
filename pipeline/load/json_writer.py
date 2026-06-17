"""Escribe el DATA canónico como JSON en data/{period_id}.json (gitignored).

period_id formato:
- "YYYY-MM" para reportes mensuales (default — coincide con regex de build_all)
- "YYYY-MM-DD" para reportes quincenales o ad-hoc
- "diagnostico" para la línea base
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.util.config import PROJECT_ROOT
from pipeline.util.log import get_logger

log = get_logger(__name__)

DATA_DIR = PROJECT_ROOT / "data"


def write_data(data: dict[str, Any], period_id: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{period_id}.json"
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("data_written", extra={"path": str(out), "size_kb": out.stat().st_size // 1024})
    return out
