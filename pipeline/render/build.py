"""Render: combina template.html + DATA (dict) → index.html final.

Reemplaza la línea con `/* DATA_INJECTION_MARKER ... */` por
    const DATA = <json minificado>;

El template se mantiene íntegro en todo lo demás (HTML, CSS, JS, Chart.js, etc.).

Uso CLI:
    python -m pipeline.render.build --data data/2026-05.json --out index.html
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline.util.config import PROJECT_ROOT
from pipeline.util.log import get_logger

log = get_logger(__name__)

TEMPLATE_PATH = PROJECT_ROOT / "pipeline" / "render" / "template.html"
DEFAULT_OUTPUT = PROJECT_ROOT / "index.html"
MARKER_RE_NEEDLE = "/* DATA_INJECTION_MARKER"   # prefix; usamos line-match


def _serialize_data(data: dict[str, Any]) -> str:
    """JSON estable, una sola línea, separadores estilo Python default."""
    # Default separators (', ', ': ') coinciden con el formato del JSON original
    return json.dumps(data, ensure_ascii=False, default=str)


def render(template: str, data: dict[str, Any]) -> str:
    """Reemplaza la línea del marker por `const DATA = <json>;`."""
    json_blob = _serialize_data(data)
    new_line = f"const DATA = {json_blob};"

    out_lines: list[str] = []
    replaced = False
    for line in template.split("\n"):
        if not replaced and line.lstrip().startswith(MARKER_RE_NEEDLE):
            out_lines.append(new_line)
            replaced = True
        else:
            out_lines.append(line)
    if not replaced:
        raise RuntimeError("Marker DATA_INJECTION_MARKER no encontrado en el template.")
    return "\n".join(out_lines)


def build(data_path: Path, out_path: Path = DEFAULT_OUTPUT, template_path: Path = TEMPLATE_PATH) -> Path:
    template = template_path.read_text(encoding="utf-8")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    rendered = render(template, data)
    out_path.write_text(rendered, encoding="utf-8")
    log.info(
        "html_rendered",
        extra={
            "data_path": str(data_path),
            "out_path": str(out_path),
            "size_kb": out_path.stat().st_size // 1024,
        },
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="ruta al JSON con el DATA")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="ruta del HTML de salida")
    parser.add_argument("--template", default=str(TEMPLATE_PATH))
    args = parser.parse_args()
    build(Path(args.data), Path(args.out), Path(args.template))
    return 0


if __name__ == "__main__":
    sys.exit(main())
