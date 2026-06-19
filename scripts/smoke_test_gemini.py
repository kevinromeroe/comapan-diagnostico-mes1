#!/usr/bin/env python3
"""Smoke test minimo de Gemini 2.5 Flash.
Hace 1 llamada con 1 prompt corto y reporta el resultado paso a paso.
Costo: 0 USD (free tier).
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_KEY = os.environ.get("GEMINI_API_KEY")
URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def main():
    print("=" * 60)
    print("SMOKE TEST — Gemini 2.5 Flash")
    print("=" * 60)

    # 1. ¿Existe la key?
    if not API_KEY:
        print("❌ FALLA: GEMINI_API_KEY no está en el entorno del runner")
        print("   Configurar en: Settings → Secrets → Actions")
        return 1
    print(f"✓ GEMINI_API_KEY presente")
    print(f"  longitud: {len(API_KEY)} chars")
    print(f"  prefijo:  {API_KEY[:8]}…")
    print(f"  sufijo:   …{API_KEY[-4:]}")

    # 2. Construir request
    prompt = "Responde solo con la palabra OK en mayusculas."
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 20}
    }
    payload = json.dumps(body).encode("utf-8")
    full_url = f"{URL}?key={API_KEY}"
    print(f"\n→ Endpoint: {URL}")
    print(f"→ Payload size: {len(payload)} bytes")

    req = urllib.request.Request(
        full_url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )

    # 3. Llamar
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
            raw = r.read().decode("utf-8")
        print(f"\n✓ HTTP {status}")
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="ignore")
        print(f"\n❌ HTTPError {e.code}")
        print(f"   Headers: {dict(e.headers)}")
        print(f"   Body: {body_err[:1000]}")
        return 1
    except Exception as e:
        print(f"\n❌ Excepción: {type(e).__name__}: {e}")
        return 1

    # 4. Parsear
    try:
        resp = json.loads(raw)
        print(f"\nRespuesta cruda (primeros 800 chars):")
        print(raw[:800])
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        usage = resp.get("usageMetadata") or {}
        print(f"\n✓ Texto: {text!r}")
        print(f"  Tokens prompt:    {usage.get('promptTokenCount')}")
        print(f"  Tokens response:  {usage.get('candidatesTokenCount')}")
        print(f"  Tokens total:     {usage.get('totalTokenCount')}")
    except Exception as e:
        print(f"\n❌ Respuesta inesperada: {type(e).__name__}: {e}")
        print(f"   Raw: {raw[:500]}")
        return 1

    print("\n" + "=" * 60)
    print("✓ SMOKE TEST OK — Gemini responde y parsea bien")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
