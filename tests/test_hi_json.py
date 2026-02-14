import datetime
import json

import pytest

from hicoros.hi.hi_json import HiJsonParser


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
