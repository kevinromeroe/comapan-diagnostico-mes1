"""Provider Anthropic — kept como opción intercambiable.

Lazy import del SDK porque puede no estar instalado en el runner si solo
usamos Gemini.
"""
from __future__ import annotations

import os

from pipeline.util.log import get_logger

log = get_logger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"


def call(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4000,
    temperature: float = 0.0,
    timeout: int = 60,
) -> str:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError(
            "Paquete 'anthropic' no instalado. pip install anthropic, "
            "o cambia provider a 'gemini' en el YAML del cliente."
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no definido.")

    client = Anthropic(api_key=api_key, timeout=timeout)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    text = msg.content[0].text
    log.info(
        "anthropic_call_ok",
        extra={
            "model": model,
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        },
    )
    return text
