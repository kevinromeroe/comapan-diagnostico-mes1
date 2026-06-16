"""Agrega los posts normalizados en buckets temporales y por tipo.

Funciones puras sobre la lista de posts normalizados que devuelve normalize.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

# Idioma fijo en español Colombia para el reporte
DAY_LABELS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def by_type(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Distribuye posts por `type` y calcula engagement promedio."""
    types: dict[str, list[int]] = defaultdict(list)
    for p in posts:
        types[p["type"]].append(p["engagement"])
    labels = sorted(types.keys())
    counts = [len(types[t]) for t in labels]
    engagement = [sum(types[t]) for t in labels]
    promedios = [round(sum(types[t]) / len(types[t]), 1) if types[t] else 0.0 for t in labels]
    return {
        "labels": labels,
        "counts": counts,
        "engagement": engagement,
        "engagement_promedio": promedios,
    }


def by_day_of_week(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa por día de la semana (Lun-Dom)."""
    buckets: dict[int, list[int]] = defaultdict(list)
    for p in posts:
        ts = p.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        buckets[ts.weekday()].append(p["engagement"])
    counts = [len(buckets[i]) for i in range(7)]
    promedios = [
        round(sum(buckets[i]) / len(buckets[i]), 1) if buckets[i] else 0.0 for i in range(7)
    ]
    return {
        "labels": DAY_LABELS_ES,
        "counts": counts,
        "engagement_promedio": promedios,
    }


def by_hour(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa por hora del día (solo horas con posts)."""
    counts: Counter = Counter()
    for p in posts:
        ts = p.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        counts[ts.hour] += 1
    labels = sorted(counts.keys())
    return {
        "labels": [str(h) for h in labels],
        "counts": [counts[h] for h in labels],
    }


def by_week(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa por semana ISO (formato YYYY-Sww)."""
    counts: dict[str, int] = defaultdict(int)
    engagement_by_week: dict[str, int] = defaultdict(int)
    for p in posts:
        ts = p.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        iso = ts.isocalendar()
        label = f"{iso.year}-S{iso.week:02d}"
        counts[label] += 1
        engagement_by_week[label] += p["engagement"]
    labels = sorted(counts.keys())
    return {
        "labels": labels,
        "counts": [counts[l] for l in labels],
        "engagement": [engagement_by_week[l] for l in labels],
    }


def top_hashtags(posts: list[dict[str, Any]], n: int = 10) -> list[list[Any]]:
    """Top N hashtags por apariciones únicas."""
    counter: Counter = Counter()
    for p in posts:
        for tag in p.get("hashtags", []):
            if tag:
                counter[tag] += 1
    return [[tag, count] for tag, count in counter.most_common(n)]


def engagement_stats(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Métricas globales agregadas."""
    engagements = [p["engagement"] for p in posts] or [0]
    return {
        "n_posts": len(posts),
        "engagement_total": sum(engagements),
        "engagement_promedio": round(sum(engagements) / len(engagements), 1) if posts else 0.0,
        "engagement_mediana": int(statistics.median(engagements)) if posts else 0,
    }


def captions_avg_len(posts: list[dict[str, Any]]) -> float:
    if not posts:
        return 0.0
    return round(sum(len(p.get("caption") or "") for p in posts) / len(posts), 1)
