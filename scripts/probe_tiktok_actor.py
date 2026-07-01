#!/usr/bin/env python3
"""Probe el actor de TikTok:
  1) Fetch input schema real (gratis)
  2) Muestra los campos requeridos y sus tipos
  3) Sugiere el input correcto basado en el schema

Uso:  python scripts/probe_tiktok_actor.py
"""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request

ACTOR_ID = "GdWCkxBtKWOsKjdch"  # clockworks/tiktok-scraper
TOKEN = os.environ.get("APIFY_TOKEN")
if not TOKEN:
    print("✗ APIFY_TOKEN no está en env")
    sys.exit(1)


def get_actor_info():
    """GET /v2/acts/{id} — devuelve metadata + inputSchema."""
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}?token={TOKEN}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_latest_success_run():
    """Ultima corrida exitosa - para ver que input SI funciono."""
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={TOKEN}&status=SUCCEEDED&desc=1&limit=1"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
        items = data.get("data", {}).get("items", [])
        return items[0] if items else None


def get_run_input(run_id):
    """Trae el INPUT que se uso en un run especifico."""
    url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={TOKEN}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    # El input esta en key-value-store OUTPUT del run
    kv_store_id = data.get("data", {}).get("defaultKeyValueStoreId")
    if not kv_store_id:
        return None
    url2 = f"https://api.apify.com/v2/key-value-stores/{kv_store_id}/records/INPUT?token={TOKEN}"
    req2 = urllib.request.Request(url2)
    try:
        with urllib.request.urlopen(req2, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError:
        return None


def main():
    print("═" * 70)
    print(f"  PROBE: clockworks/tiktok-scraper  (id: {ACTOR_ID})")
    print("═" * 70)

    # 1) Actor info + schema
    try:
        info = get_actor_info()
        d = info.get("data", {})
        print(f"\nName:          {d.get('username')}/{d.get('name')}")
        print(f"Version:       {d.get('versions', [{}])[0].get('versionNumber', '?')}")
        print(f"Modified:      {d.get('modifiedAt')}")
        # inputSchema esta en versions[0].sourceFiles o dentro de sourceType
        # Puede que no venga con /acts/, hay que pedirlo explicito con view=default
    except Exception as e:
        print(f"✗ Info fallo: {e}")

    # 2) Ultima corrida exitosa → ver su input
    print(f"\n── Últimos runs exitosos (que input les funcionó) ──")
    try:
        last_ok = get_latest_success_run()
        if not last_ok:
            print("  ✗ Sin runs exitosos históricos")
        else:
            print(f"  Run: {last_ok.get('id')}  finalizado: {last_ok.get('finishedAt')}")
            print(f"  Items retornados: {last_ok.get('stats', {}).get('outputBodyBytes', '?')} bytes")
            inp = get_run_input(last_ok["id"])
            if inp is None:
                print("  ✗ No pude leer el INPUT del key-value-store")
            else:
                print(f"\n  INPUT que SI funciono (usar como referencia):")
                print(json.dumps(inp, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"  ✗ Fallo: {e}")

    # 3) Comparar con el input actual en nuestro yaml
    print(f"\n── Nuestro input actual en config/clients/comapan.yaml ──")
    import yaml
    try:
        with open("config/clients/comapan.yaml") as f:
            cfg = yaml.safe_load(f)
        current_input = cfg["platforms"]["tiktok"]["apify"]["posts"]["input"]
        print(json.dumps(current_input, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"  ✗ Fallo leyendo yaml: {e}")

    print("\n══ Comparar los 2 inputs. Ajustar el yaml para que matchee al que funcionó. ══")


if __name__ == "__main__":
    main()
