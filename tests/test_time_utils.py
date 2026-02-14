from datetime import datetime, timezone

import pytest

from hicoros.time_utils import convert_hitrack_timestamp
from hicoros.time_utils import get_tz_aware_datetime


def test_convert_hitrack_timestamp_epoch_seconds():
    dt = convert_hitrack_timestamp(1_700_000_000)
    assert dt.tzinfo == timezone.utc
    assert dt.year >= 2023


def test_convert_hitrack_timestamp_relative_to_reference():
    ref = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    dt = convert_hitrack_timestamp(60, timestamp_ref=ref)
    assert dt == datetime(2025, 1, 1, 0, 1, 0, tzinfo=timezone.utc)


def test_convert_hitrack_timestamp_preserves_millisecond_precision():
    dt = convert_hitrack_timestamp(1_700_000_000_123)
    assert dt.microsecond == 123000


def test_convert_hitrack_timestamp_relative_preserves_fractional_seconds():
    ref = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    dt = convert_hitrack_timestamp(60.125, timestamp_ref=ref)
    assert dt == datetime(2025, 1, 1, 0, 1, 0, 125000, tzinfo=timezone.utc)


def test_get_tz_aware_datetime_defaults_to_utc_when_no_timezone():
    naive = datetime(2025, 1, 1, 12, 0, 0)
    aware = get_tz_aware_datetime(naive, None)
    assert aware.tzinfo == timezone.utc


def test_get_tz_aware_datetime_converts_to_target_timezone():
    naive = datetime(2025, 1, 1, 12, 0, 0)
    plus_one = timezone.utc
    aware = get_tz_aware_datetime(naive, plus_one)
    assert aware.tzinfo == plus_one


def test_convert_hitrack_timestamp_raises_on_invalid_zero():
    with pytest.raises(ValueError):
        convert_hitrack_timestamp(0)
