"""Escribe el DATA canónico como JSON en data/YYYY-MM-DD.json (gitignored)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.util.config import PROJECT_ROOT
from pipeline.util.log import get_logger

log = get_logger(__name__)

DATA_DIR = PROJECT_ROOT / "data"


def write_data(data: dict[str, Any], snapshot: date) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"{snapshot.isoformat()}.json"
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("data_written", extra={"path": str(out), "size_kb": out.stat().st_size // 1024})
    return out
