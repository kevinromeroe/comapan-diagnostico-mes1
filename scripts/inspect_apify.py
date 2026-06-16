#!/usr/bin/env python3
"""
inspect_apify.py — herramienta operacional para mapear shapes de actores Apify.

Descarga muestras de items de cada dataset configurado, las guarda como
fixtures en tests/fixtures/ y genera un resumen de los campos disponibles
para documentar en docs/apify_schemas/.

Uso:
    python scripts/inspect_apify.py                    # mapea todos los runs recientes
    python scripts/inspect_apify.py --dataset <id>     # mapea un dataset específico
    python scripts/inspect_apify.py --list-runs        # lista runs sin descargar

Variables de entorno:
    APIFY_TOKEN     (obligatorio)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.apify.com/v2"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
SCHEMAS_DIR = PROJECT_ROOT / "docs" / "apify_schemas"


def get_token() -> str:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("ERROR: env var APIFY_TOKEN no definida.")
    return token


def call_apify(path: str, token: str, params: dict[str, Any] | None = None) -> Any:
    """GET contra Apify API. Devuelve el JSON parseado."""
    params = {**(params or {}), "token": token}
    url = f"{API_BASE}{path}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "datalitica-inspector/1.0"})
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_recent_runs(token: str, limit: int = 20) -> list[dict[str, Any]]:
    """Lista los runs recientes del usuario."""
    data = call_apify("/actor-runs", token, {"limit": limit, "desc": 1})
    return data["data"]["items"]


def get_actor_info(actor_id: str, token: str) -> dict[str, Any]:
    """Devuelve metadata del actor (name, username, etc)."""
    data = call_apify(f"/acts/{actor_id}", token)
    return data["data"]


def fetch_dataset_items(
    dataset_id: str, token: str, limit: int = 5, clean: bool = True
) -> list[dict[str, Any]]:
    """Trae los primeros N items del dataset."""
    params = {"limit": limit, "format": "json"}
    if clean:
        params["clean"] = "true"
    data = call_apify(f"/datasets/{dataset_id}/items", token, params)
    if isinstance(data, list):
        return data
    return data.get("data", [])


def flatten_keys(obj: Any, prefix: str = "") -> list[str]:
    """Lista todos los paths de campos en un dict anidado."""
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.append(full)
            keys.extend(flatten_keys(v, full))
    elif isinstance(obj, list) and obj:
        keys.extend(flatten_keys(obj[0], f"{prefix}[]"))
    return keys


def field_summary(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Resume qué campos están presentes y con qué tipos."""
    seen: dict[str, set] = defaultdict(set)
    sample: dict[str, Any] = {}
    for item in items:
        for path in flatten_keys(item):
            seen[path].add(type(_get_path(item, path)).__name__)
            if path not in sample:
                sample[path] = _get_path(item, path)
    return {
        path: {
            "types": sorted(types),
            "sample": _truncate(sample.get(path)),
        }
        for path, types in sorted(seen.items())
    }


def _get_path(obj: Any, path: str) -> Any:
    """Navega un path tipo 'a.b[].c'."""
    cur = obj
    for part in path.split("."):
        if part.endswith("[]"):
            key = part[:-2]
            cur = (cur.get(key) if isinstance(cur, dict) else None) or []
            cur = cur[0] if cur else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _truncate(value: Any, max_len: int = 80) -> Any:
    """Recorta strings largos para que el resumen sea legible."""
    if isinstance(value, str) and len(value) > max_len:
        return value[: max_len - 3] + "..."
    return value


def save_fixture(actor_name: str, run_id: str, items: list[dict[str, Any]]) -> Path:
    """Guarda los items capturados como fixture versionable."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    safe = actor_name.replace("/", "_").replace("-", "_")
    fname = f"apify_{safe}_{run_id[:8]}.json"
    fpath = FIXTURES_DIR / fname
    with fpath.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return fpath


def print_summary(actor_name: str, dataset_id: str, summary: dict) -> None:
    print(f"\n{'='*70}\nActor: {actor_name}\nDataset: {dataset_id}\nCampos detectados: {len(summary)}\n{'='*70}")
    for path, info in summary.items():
        types = "|".join(info["types"])
        sample = info["sample"]
        print(f"  {path:<55} {types:<15} sample={sample!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", help="ID específico de dataset a mapear")
    parser.add_argument("--limit", type=int, default=5, help="Items a traer")
    parser.add_argument("--list-runs", action="store_true", help="Solo listar runs")
    parser.add_argument("--save-fixtures", action="store_true", help="Guardar como fixture")
    args = parser.parse_args()

    token = get_token()

    if args.list_runs:
        runs = list_recent_runs(token)
        print(f"\n{'RUN_ID':<20} {'ACTOR_ID':<20} {'STATUS':<10} {'DATASET':<20} STARTED")
        for r in runs:
            print(
                f"{r['id']:<20} {r['actId']:<20} {r['status']:<10} "
                f"{r['defaultDatasetId']:<20} {r.get('startedAt','-')}"
            )
        return

    if args.dataset:
        targets = [(None, args.dataset)]
    else:
        runs = list_recent_runs(token)
        targets = [(r["actId"], r["defaultDatasetId"]) for r in runs if r["status"] == "SUCCEEDED"]

    for act_id, dataset_id in targets:
        try:
            items = fetch_dataset_items(dataset_id, token, limit=args.limit)
        except Exception as exc:
            print(f"⚠️  Dataset {dataset_id}: {exc}")
            continue
        if not items:
            print(f"⚠️  Dataset {dataset_id}: vacío")
            continue
        actor_info = get_actor_info(act_id, token) if act_id else {"name": "unknown"}
        actor_name = f"{actor_info.get('username','?')}/{actor_info.get('name','?')}"
        summary = field_summary(items)
        print_summary(actor_name, dataset_id, summary)
        if args.save_fixtures:
            fpath = save_fixture(actor_name, dataset_id, items)
            print(f"  ✅ fixture guardada: {fpath.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
