"""Tests de aggregate — funciones puras sobre posts normalizados."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pipeline.transform import aggregate


def _post(engagement: int, ts: datetime, ptype: str = "Video", hashtags=None) -> dict:
    return {
        "id": "x",
        "url": "",
        "type": ptype,
        "caption": "lorem ipsum",
        "hashtags": hashtags or [],
        "timestamp": ts,
        "likes": engagement // 2,
        "comments": engagement - (engagement // 2),
        "shares": 0,
        "engagement": engagement,
        "extra": {},
        "media_url": None,
    }


def test_by_type_groups_correctly():
    posts = [
        _post(100, datetime(2026, 5, 1, tzinfo=timezone.utc), "Video"),
        _post(50, datetime(2026, 5, 2, tzinfo=timezone.utc), "Video"),
        _post(20, datetime(2026, 5, 3, tzinfo=timezone.utc), "Image"),
    ]
    out = aggregate.by_type(posts)
    assert out["labels"] == ["Image", "Video"]
    assert out["counts"] == [1, 2]
    assert out["engagement"] == [20, 150]
    assert out["engagement_promedio"] == [20.0, 75.0]


def test_by_day_of_week_uses_es_labels():
    monday = datetime(2026, 5, 4, tzinfo=timezone.utc)  # lunes
    posts = [_post(10, monday)]
    out = aggregate.by_day_of_week(posts)
    assert out["labels"][0] == "Lun"
    assert out["counts"][0] == 1
    assert out["engagement_promedio"][0] == 10.0


def test_by_hour_only_hours_with_posts():
    posts = [
        _post(10, datetime(2026, 5, 1, 8, tzinfo=timezone.utc)),
        _post(20, datetime(2026, 5, 2, 17, tzinfo=timezone.utc)),
        _post(30, datetime(2026, 5, 3, 17, tzinfo=timezone.utc)),
    ]
    out = aggregate.by_hour(posts)
    assert out["labels"] == ["8", "17"]
    assert out["counts"] == [1, 2]


def test_by_week_iso_format():
    posts = [
        _post(10, datetime(2026, 1, 5, tzinfo=timezone.utc)),  # 2026-W02
        _post(20, datetime(2026, 1, 12, tzinfo=timezone.utc)),  # 2026-W03
        _post(30, datetime(2026, 1, 13, tzinfo=timezone.utc)),  # 2026-W03
    ]
    out = aggregate.by_week(posts)
    assert "2026-S02" in out["labels"]
    assert "2026-S03" in out["labels"]
    # engagement de W03 debe ser 50
    idx = out["labels"].index("2026-S03")
    assert out["engagement"][idx] == 50


def test_top_hashtags_counts_unique():
    posts = [
        _post(10, datetime(2026, 5, 1, tzinfo=timezone.utc), hashtags=["a", "b"]),
        _post(20, datetime(2026, 5, 2, tzinfo=timezone.utc), hashtags=["a"]),
        _post(30, datetime(2026, 5, 3, tzinfo=timezone.utc), hashtags=["c"]),
    ]
    out = aggregate.top_hashtags(posts, n=10)
    assert out[0] == ["a", 2]
    assert ["b", 1] in out
    assert ["c", 1] in out


def test_engagement_stats_empty():
    out = aggregate.engagement_stats([])
    assert out["n_posts"] == 0
    assert out["engagement_total"] == 0


def test_engagement_stats_basic():
    posts = [
        _post(10, datetime(2026, 5, 1, tzinfo=timezone.utc)),
        _post(20, datetime(2026, 5, 2, tzinfo=timezone.utc)),
        _post(30, datetime(2026, 5, 3, tzinfo=timezone.utc)),
    ]
    out = aggregate.engagement_stats(posts)
    assert out["n_posts"] == 3
    assert out["engagement_total"] == 60
    assert out["engagement_promedio"] == 20.0
    assert out["engagement_mediana"] == 20
