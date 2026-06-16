"""Wrapper minimalista sobre la API REST de Apify.

Razón de no usar `apify-client` oficial: queremos control fino sobre retries,
timeouts y manejo de errores específico a nuestro caso, sin agregar una
dependencia más a la pipeline.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterator
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from pipeline.util.log import get_logger

API_BASE = "https://api.apify.com/v2"
log = get_logger(__name__)


class ApifyError(Exception):
    pass


class ApifyClient:
    def __init__(
        self,
        token: str,
        *,
        max_attempts: int = 3,
        backoff_seconds: list[int] | None = None,
        timeout: int = 60,
    ) -> None:
        self.token = token
        self.max_attempts = max_attempts
        self.backoff = backoff_seconds or [5, 15, 45]
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = {**(params or {}), "token": self.token}
        url = f"{API_BASE}{path}?{urlencode(params)}"
        last_exc: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                req = Request(url, headers={"User-Agent": "datalitica-pipeline/1.0"})
                with urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body) if body else None
            except (HTTPError, URLError, TimeoutError) as exc:
                last_exc = exc
                if attempt + 1 < self.max_attempts:
                    sleep_for = self.backoff[min(attempt, len(self.backoff) - 1)]
                    log.warning(
                        "apify_request_retry",
                        extra={
                            "path": path,
                            "attempt": attempt + 1,
                            "next_sleep_s": sleep_for,
                            "error": str(exc),
                        },
                    )
                    time.sleep(sleep_for)
        raise ApifyError(f"GET {path} failed after {self.max_attempts} attempts: {last_exc}")

    def dataset_items(
        self, dataset_id: str, *, limit: int | None = None, clean: bool = True
    ) -> list[dict[str, Any]]:
        """Trae todos los items de un dataset, con paginación interna."""
        items: list[dict[str, Any]] = []
        offset = 0
        page_size = 500
        while True:
            params: dict[str, Any] = {
                "format": "json",
                "clean": str(clean).lower(),
                "limit": page_size,
                "offset": offset,
            }
            page = self._get(f"/datasets/{dataset_id}/items", params) or []
            if not isinstance(page, list):
                raise ApifyError(f"Unexpected dataset response shape: {type(page)}")
            items.extend(page)
            if len(page) < page_size or (limit and len(items) >= limit):
                break
            offset += page_size
        if limit:
            items = items[:limit]
        log.info(
            "apify_dataset_fetched",
            extra={"dataset_id": dataset_id, "items": len(items)},
        )
        return items

    def last_succeeded_run_for_actor(self, actor_id: str) -> dict[str, Any] | None:
        """Última corrida exitosa de un actor (cualquier task)."""
        data = self._get(f"/acts/{actor_id}/runs", {"status": "SUCCEEDED", "desc": 1, "limit": 1})
        items = data["data"]["items"] if data else []
        return items[0] if items else None
