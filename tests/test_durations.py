from datetime import timedelta

import pytest

from itsm_insights.durations import format_duration, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15m", timedelta(minutes=15)),
        ("4h", timedelta(hours=4)),
        ("3d", timedelta(days=3)),
        ("1w", timedelta(weeks=1)),
        ("90s", timedelta(seconds=90)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        ("1h 30m", timedelta(hours=1, minutes=30)),
        ("1.5h", timedelta(minutes=90)),
        (" 4H ", timedelta(hours=4)),
        (30, timedelta(minutes=30)),
        (timedelta(hours=2), timedelta(hours=2)),
    ],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("bad", ["", "15", "h", "4x", "4h abc", "-4h", "abc4h", True, -5])
def test_parse_duration_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (timedelta(days=2, hours=4, minutes=10), "2d 4h"),
        (timedelta(hours=3, minutes=15), "3h 15m"),
        (timedelta(minutes=45), "45m"),
        (timedelta(seconds=30), "30s"),
        (timedelta(0), "0s"),
        (None, "-"),
        (float("nan"), "-"),
        (5400.0, "1h 30m"),
    ],
)
def test_format_duration(value, expected):
    assert format_duration(value) == expected
