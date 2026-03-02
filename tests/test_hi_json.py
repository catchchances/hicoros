import datetime
import json

import pytest

from hicoros.hi.hi_json import HiJsonParser
from hicoros.hi.hi_activity import HiActivity


def test_hi_activity_timer_duration_defaults_to_none():
    """HiActivity.timer_duration must be None until the source format provides it."""
    activity = HiActivity("test_activity")
    assert activity.timer_duration is None


def test_hi_json_parser_sets_timer_duration_from_total_time(tmp_path):
    """HiJsonParser must store totalTime / 1000.0 as timer_duration on the parsed activity."""
    hitrack_content = (
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=100\n"
        "tp=lbs;k=1;lat=39.9043;lon=116.4075;alt=0;t=200\n"
    )
    attribute = f"HW_EXT_TRACK_DETAIL@is{hitrack_content}&&HW_EXT_TRACK_SIMPLIFY@is{{}}"

    json_data = [
        {
            "recordDay": 20240101,
            "startTime": 1704067200000,  # 2024-01-01 00:00:00 UTC in ms
            "timeZone": "+0000",
            "totalTime": 9000000,  # 9000 s = 2.5 hours in ms
            "sportType": 4,  # RUN
            "attribute": attribute,
        }
    ]

    json_path = tmp_path / "activities.json"
    json_path.write_text(json.dumps(json_data), encoding="utf-8")

    parser = HiJsonParser(str(json_path), output_dir=str(tmp_path))
    activities = parser.parse(from_date=datetime.date(1970, 1, 1))

    assert len(activities) == 1
    assert activities[0].timer_duration == pytest.approx(9000.0)


def test_hi_json_parse_error_message_is_standardized_at_entry(tmp_path):
    json_path = tmp_path / "activities.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "recordDay": 20240101,
                    "startTime": 1700000000000,
                    "timeZone": "+0000",
                    "attribute": "HW_EXT_TRACK_DETAIL@is"
                }
            ]
        ),
        encoding="utf-8",
    )

    parser = HiJsonParser(str(json_path), output_dir=str(tmp_path))

    with pytest.raises(Exception) as exc_info:
        parser.parse(from_date=datetime.date(1970, 1, 1))

    message = str(exc_info.value)
    assert "activity index <0>" in message
    assert "Raw snippet:" in message
    assert "'startTime': 1700000000000" in message
    assert "KeyError:" in message
