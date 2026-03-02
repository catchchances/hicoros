from pathlib import Path
from datetime import timedelta

import pytest

from hicoros.hi.hi_track_file import HiTrackFileParser
from hicoros.hi.hi_activity import HiActivity


def test_hitrack_file_parse_minimal_location_line(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text("tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n", encoding="utf-8")

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    assert activity.activity_id == hitrack_name
    assert activity.start is not None
    assert activity.stop is not None


def test_hitrack_file_parse_step_frequency_k_as_relative_minutes(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=s-r;k=2;v=168\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(minutes=2)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["s-r"] == 168


def test_hitrack_file_parse_step_frequency_reads_k_v_by_key(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=s-r;foo=bar;v=172;k=2\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(minutes=2)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["s-r"] == 172


def test_hitrack_file_parse_heart_rate_k_as_relative_minutes(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=h-r;k=3;v=145\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(minutes=3)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["hr"] == 145


def test_hitrack_file_parse_altitude_k_as_relative_seconds_with_5s_offset(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=alti;k=10;v=123.4\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=15)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["alti"] == 123.4


def test_hitrack_file_ignores_tp_alt_and_only_parses_tp_alti(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;t=1700000000\n"
        "tp=alt;k=10;v=111.1\n"
        "tp=alti;k=10;v=123.4\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=15)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["alti"] == 123.4


def test_hitrack_file_parse_interval_pace_metric_pm_n(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=pm-n;k=2;v=290\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=15)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["pm-n"] == 290.0


def test_hitrack_file_parse_pace_p_m(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=p-m;k=2;v=300\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=15)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["p-m"] == 300.0


def test_hitrack_file_parse_realtime_speed_rs_k_as_seconds(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=rs;k=12;v=45\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=12)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["rs"] == 45.0


def test_hitrack_file_parse_realtime_speed_pace_r_pm(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=r-pm;k=12;s=10.8;P=300\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=12)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["r-pm-s"] == 10.8
    assert activity.data_dict[expected_ts]["r-pm-p"] == 300.0


def test_hitrack_file_parse_heart_rate_k_as_absolute_epoch_millis(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=h-r;k=1700000005000;v=145\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=5)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["hr"] == 145


def test_hitrack_file_parse_altitude_k_as_absolute_epoch_millis(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=alti;k=1700000005000;v=123.4\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=5)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["alti"] == 123.4


def test_hitrack_file_parse_step_frequency_k_as_absolute_epoch_millis(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=s-r;k=1700000005000;v=168\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    expected_ts = activity.start + timedelta(seconds=5)
    assert expected_ts in activity.data_dict
    assert activity.data_dict[expected_ts]["s-r"] == 168


def test_hitrack_file_parse_lbs_does_not_set_alti(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=123.4;t=1700000000\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    assert activity.start in activity.data_dict
    assert activity.data_dict[activity.start]["lbs-k"] == 0.0
    assert "k" not in activity.data_dict[activity.start]
    assert "alti" not in activity.data_dict[activity.start]


def test_hitrack_parse_speed_record_during_pause_does_not_cause_index_error(tmp_path: Path):
    """Speed record (tp=rs) appearing during a manual pause must not corrupt the Vincenty
    pre-calc distance count.  Before the pre_paused fix, the RS record with time_delta >
    GPS_TIMEOUT would overwrite pre_last_location, making the pre-calc batch produce one
    fewer distance pair than the main loop expected, causing an IndexError when GPS resumed."""
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        # Real GPS fix
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        # Manual pause marker (lat=90, lon=-80)
        "tp=lbs;k=1;lat=90;lon=-80;alt=0;t=1700000030\n"
        # Speed record 50 s after activity start (> GPS_TIMEOUT=10 s), while still paused
        "tp=rs;k=50;v=30\n"
        # GPS resumes after pause
        "tp=lbs;k=2;lat=39.9050;lon=116.4080;alt=0;t=1700000100\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))
    activity = parser.parse()

    assert activity is not None
    segments = activity.get_segments()
    # Expect two segments: before and after the pause
    assert len(segments) == 2
    assert all(seg.get("start") is not None and seg.get("stop") is not None for seg in segments)


def test_hitrack_file_parse_raises_original_exception(tmp_path: Path):
    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=h-r;k=bad;v=145\n",
        encoding="utf-8",
    )

    parser = HiTrackFileParser(str(hitrack_path))

    with pytest.raises(ValueError) as exc_info:
        parser.parse()

    assert "could not convert string to float" in str(exc_info.value)
