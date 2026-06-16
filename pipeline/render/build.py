"""Render: template.html + (DATA + REPORT_META) → index.html final.

Modos:
    1. **single**: --data <json> --out <path>
       Genera UN HTML con esa data inyectada. Útil para previews locales.

    2. **multi (default cuando hay varios periodos disponibles)**: --build-all
       Lee data/diagnostico.json + todos los data/2026-MM.json,
       genera /diagnostico/index.html, /2026-MM/index.html por cada uno,
       y copia el más reciente como /index.html (raíz).

Inyecta dos cosas en el template:
    - const DATA = {...};            (los datos del período actual)
    - const REPORT_META = {...};     (lista de períodos disponibles, el actual,
                                       y URLs para el selector de fechas)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from pipeline.util.config import PROJECT_ROOT
from pipeline.util.log import get_logger

log = get_logger(__name__)

TEMPLATE_PATH = PROJECT_ROOT / "pipeline" / "render" / "template.html"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT = PROJECT_ROOT / "index.html"

DATA_MARKER = "/* DATA_INJECTION_MARKER"
PERIODS_MARKER = "/* PERIODS_INJECTION_MARKER"

MONTH_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _serialize(obj: Any) -> str:
    """JSON estable, una sola línea, separadores estilo Python default."""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _period_label(period_id: str) -> str:
    """Genera el label legible para el selector. 'diagnostico' → 'Diagnóstico (May 2026)'."""
    if period_id == "diagnostico":
        return "Diagnóstico (cierre may 2026)"
    # YYYY-MM
    m = re.match(r"^(\d{4})-(\d{2})$", period_id)
    if m:
        year, month = m.groups()
        return f"{MONTH_ES[int(month)]} {year}"
    return period_id


def _period_url(period_id: str) -> str:
    """Path relativo al cual apunta el option del selector."""
    if period_id == "diagnostico":
        return "/diagnostico/"
    return f"/{period_id}/"


def list_available_periods() -> list[str]:
    """Inventario de períodos: diagnostico (siempre) + cualquier YYYY-MM.json en data/."""
    periods: list[str] = []
    if (DATA_DIR / "diagnostico.json").exists():
        periods.append("diagnostico")
    for path in sorted(DATA_DIR.glob("2*.json")):
        stem = path.stem
        if re.match(r"^\d{4}-\d{2}$", stem):
            periods.append(stem)
    return periods


def build_report_meta(current_period: str, available: list[str]) -> dict[str, Any]:
    return {
        "current": current_period,
        "available": [
            {"id": pid, "label": _period_label(pid), "url": _period_url(pid)}
            for pid in available
        ],
    }


def render(template: str, data: dict[str, Any], report_meta: dict[str, Any]) -> str:
    """Reemplaza ambos markers por las constantes correspondientes."""
    out_lines: list[str] = []
    data_replaced = periods_replaced = False
    for line in template.split("\n"):
        stripped = line.lstrip()
        if not data_replaced and stripped.startswith(DATA_MARKER):
            out_lines.append(f"const DATA = {_serialize(data)};")
            data_replaced = True
        elif not periods_replaced and stripped.startswith(PERIODS_MARKER):
            out_lines.append(f"const REPORT_META = {_serialize(report_meta)};")
            periods_replaced = True
        else:
            out_lines.append(line)
    if not data_replaced:
        raise RuntimeError("DATA_INJECTION_MARKER no encontrado en el template.")
    if not periods_replaced:
        # No es fatal si falta — el sitio funciona sin selector
        log.warning("periods_marker_missing")
    return "\n".join(out_lines)


def build_one(
    data_path: Path,
    out_path: Path,
    *,
    available_periods: list[str] | None = None,
    template_path: Path = TEMPLATE_PATH,
) -> Path:
    """Genera un único HTML."""
    template = template_path.read_text(encoding="utf-8")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    current = data_path.stem
    available = available_periods or list_available_periods()
    report_meta = build_report_meta(current, available)
    rendered = render(template, data, report_meta)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    log.info(
        "html_rendered",
        extra={"period": current, "out": str(out_path), "size_kb": out_path.stat().st_size // 1024},
    )
    return out_path


def build_all() -> dict[str, Path]:
    """Genera HTMLs para todos los periodos disponibles + index.html raíz."""
    available = list_available_periods()
    if not available:
        raise RuntimeError("No hay JSONs en data/ para renderizar.")

    outputs: dict[str, Path] = {}
    for pid in available:
        data_path = DATA_DIR / f"{pid}.json"
        # subruta: /diagnostico/index.html y /YYYY-MM/index.html
        sub = "diagnostico" if pid == "diagnostico" else pid
        out = PROJECT_ROOT / sub / "index.html"
        outputs[pid] = build_one(data_path, out, available_periods=available)

    # Raíz: copia del periodo más reciente que no sea diagnostico (si existe), si no diagnostico
    non_diag = [p for p in available if p != "diagnostico"]
    latest = non_diag[-1] if non_diag else "diagnostico"
    shutil.copy(outputs[latest], PROJECT_ROOT / "index.html")
    outputs["__root__"] = PROJECT_ROOT / "index.html"
    log.info("root_updated", extra={"from_period": latest})
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="ruta al JSON de un período (modo single)")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="ruta de salida (modo single)")
    parser.add_argument("--build-all", action="store_true",
                        help="genera todos los periodos + raíz (modo multi)")
    parser.add_argument("--template", default=str(TEMPLATE_PATH))
    args = parser.parse_args()

    if args.build_all:
        outs = build_all()
        for k, v in outs.items():
            print(f"  ✓ {k:<14} → {v}")
    elif args.data:
        build_one(Path(args.data), Path(args.out), template_path=Path(args.template))
    else:
        parser.error("Especifica --data o --build-all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
