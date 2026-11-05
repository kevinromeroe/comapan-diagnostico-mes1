#!/usr/bin/env python3
"""restaurar_seguidores.py — Devuelve a Supabase los seguidores de un mes tal como
quedaron publicados en una versión anterior del dashboard (historial de git).

Sirve cuando una reingesta pisó el snapshot de seguidores de un mes con un dato
de otra fecha. Solo toca followers y snapshot_at de la tabla accounts.

Uso (en workflow, con el repo completo):
    python scripts/restaurar_seguidores.py --period 2026-10 --ref 9630c9d
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.load.supabase_client import Supabase

CLIENT_ID = "comapan"
PLATFORM_KEY = {"Instagram": "instagram", "Facebook": "facebook",
                "TikTok": "tiktok", "LinkedIn": "linkedin"}


def accounts_publicados(period: str, ref: str) -> dict:
    html = subprocess.run(["git", "show", f"{ref}:{period}/index.html"],
                          capture_output=True, check=True).stdout.decode("utf-8")
    line = next(l for l in html.split("\n") if l.lstrip().startswith("const DATA = "))
    data = json.loads(line.strip()[len("const DATA = "):].rstrip().rstrip(";"))
    return data.get("accounts") or {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", required=True, help="Mes a restaurar (YYYY-MM)")
    parser.add_argument("--ref", required=True, help="Commit con la versión publicada correcta")
    args = parser.parse_args()

    sb = Supabase()
    cambios = 0
    for cap, acc in accounts_publicados(args.period, args.ref).items():
        platform = PLATFORM_KEY.get(cap)
        seguidores = acc.get("seguidores")
        if not platform or not seguidores:
            print(f"  · {cap}: sin seguidores en {args.ref}, no se toca")
            continue
        sb.update("accounts",
                  f"client_id=eq.{CLIENT_ID}&period_id=eq.{args.period}&platform=eq.{platform}",
                  {"followers": int(seguidores), "snapshot_at": acc.get("snapshot_fecha") or None})
        print(f"  ✓ {platform}: {int(seguidores)} (snapshot {acc.get('snapshot_fecha')})")
        cambios += 1

    print(f"\n✅ {cambios} redes restauradas para {args.period} desde {args.ref}.")
    return 0 if cambios else 1


if __name__ == "__main__":
    sys.exit(main())
