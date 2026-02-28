from datetime import datetime
from datetime import timedelta
import json
from pathlib import Path

import pytest

from hicoros.fit.fit_writer import _compute_altitude_gain_loss
from hicoros.fit.fit_writer import _compute_avg_heart_rate
from hicoros.fit.fit_writer import _compute_avg_cadence
from hicoros.fit.fit_writer import _compute_max_heart_rate
from hicoros.fit.fit_writer import _compute_max_cadence
from hicoros.fit.fit_writer import _compute_avg_cadence_from_cycles
from hicoros.fit.fit_writer import _compute_speed_stats
from hicoros.fit.fit_writer import _compute_total_calories
from hicoros.fit.fit_writer import _build_distance_laps
from hicoros.fit.fit_writer import _distribute_calories_by_distance
from hicoros.fit.fit_writer import _derive_record_speed_from_raw_rs
from hicoros.fit.fit_writer import _compute_max_speed_from_raw_rs
from hicoros.fit.fit_writer import build_fit_filename
from hicoros.fit.fit_writer import _compute_summary_values
from hicoros.fit.fit_writer import save_fit_file
from hicoros.hi.hi_activity import HiActivity
from hicoros.hi.hi_track_file import HiTrackFileParser


class DummyActivity:
    def __init__(self):
        self.start = datetime(2025, 1, 2, 3, 4, 5)
        self.time_zone = None


def test_build_fit_filename_includes_timestamp():
    hi_activity = DummyActivity()

    filename = build_fit_filename("/tmp/out", hi_activity)
    assert filename.endswith("/HiTrack_20250102_030405.fit")


def test_compute_summary_values_prefers_lap_and_record_consistency():
    start_ts, stop_ts, elapsed, timer, distance = _compute_summary_values(
        default_start_ts=1000,
        default_stop_ts=5000,
        default_elapsed=4,
        default_distance=24670.0,
        first_lap_start_ts=1000,
        last_lap_stop_ts=13072,
        lap_total_timer=9.843,
        lap_total_distance=24670.55,
        first_record_ts=1000,
        last_record_ts=9740,
        last_record_distance=24670.53,
    )

    assert start_ts == 1000
    assert stop_ts == 13072
    assert elapsed == 12.072
    assert timer == 9.843
    assert distance == 24670.55


def test_compute_altitude_gain_loss_from_track_points():
    points = [
        {"alti": 100},
        {"alti": 105},
        {"alti": 103},
        {"alti": 110},
        {"alti": 108},
    ]

    ascent, descent = _compute_altitude_gain_loss(points)

    assert ascent == 12.0
    assert descent == 4.0


def test_compute_total_calories_rounds_positive_values_only():
    class DummyActivityWithCalories:
        def __init__(self, calories):
            self.calories = calories

    assert _compute_total_calories(DummyActivityWithCalories(486.6)) == 487
    assert _compute_total_calories(DummyActivityWithCalories(0)) is None
    assert _compute_total_calories(DummyActivityWithCalories(-3)) is None


def test_distribute_calories_by_distance_keeps_total_and_ratio():
    distribution = _distribute_calories_by_distance(100, [1.0, 2.0, 1.0])

    assert distribution == [25, 50, 25]
    assert sum(distribution) == 100


def test_distribute_calories_by_distance_uses_remainder_fairly():
    distribution = _distribute_calories_by_distance(10, [1.0, 1.0, 1.0])

    assert sum(distribution) == 10
    assert sorted(distribution) == [3, 3, 4]


def test_distribute_calories_by_distance_returns_none_for_invalid_input():
    assert _distribute_calories_by_distance(0, [1.0, 2.0]) is None
    assert _distribute_calories_by_distance(100, []) is None
    assert _distribute_calories_by_distance(100, [0.0, 0.0]) is None


def test_compute_speed_stats_from_distance_over_time():
    points = [
        {"timestamp": 0, "distance": 0.0},
        {"timestamp": 1000, "distance": 5.0},
        {"timestamp": 2000, "distance": 15.0},
    ]

    avg_speed, max_speed = _compute_speed_stats(points)

    assert avg_speed == 7.5
    assert max_speed == 10.0


def test_compute_speed_stats_prefers_raw_rs_sampling_interval():
    points = [
        {"timestamp": 0, "distance": 0.0, "rs": 30},
        {"timestamp": 1000, "distance": 3.0},
        {"timestamp": 2000, "distance": 6.0},
        {"timestamp": 3000, "distance": 9.0},
        {"timestamp": 4000, "distance": 12.0},
        {"timestamp": 5000, "distance": 15.0, "rs": 40},
    ]

    avg_speed, max_speed = _compute_speed_stats(points, allow_distance_fallback=False)

    assert avg_speed == 3.0
    assert max_speed == 4.0


def test_derive_record_speed_from_raw_rs_only():
    assert _derive_record_speed_from_raw_rs({"rs": 30.0}) == 3.0
    assert _derive_record_speed_from_raw_rs({"distance": 100.0}) is None


def test_derive_record_speed_from_pm_n_when_rs_missing():
    assert _derive_record_speed_from_raw_rs({"pm-n": 250.0}) == pytest.approx(4.0)


def test_derive_record_speed_prefers_rs_over_pm_n():
    assert _derive_record_speed_from_raw_rs({"rs": 30.0, "pm-n": 200.0}) == 3.0


def test_derive_record_speed_prefers_r_pm_speed_over_rs():
    assert _derive_record_speed_from_raw_rs({"rs": 30.0, "r-pm-s": 14.4}) == pytest.approx(4.0)


def test_derive_record_speed_prefers_r_pm_pace_over_rs():
    assert _derive_record_speed_from_raw_rs({"rs": 30.0, "r-pm-p": 200.0}) == pytest.approx(5.0)


def test_derive_record_speed_from_p_m_when_rs_missing():
    assert _derive_record_speed_from_raw_rs({"p-m": 250.0}) == pytest.approx(4.0)


def test_derive_record_speed_from_r_pm_speed_when_rs_missing():
    assert _derive_record_speed_from_raw_rs({"r-pm-s": 10.8}) == pytest.approx(3.0)


def test_derive_record_speed_from_r_pm_pace_when_speed_missing():
    assert _derive_record_speed_from_raw_rs({"r-pm-p": 250.0}) == pytest.approx(4.0)


def test_compute_max_speed_from_raw_rs_returns_none_without_rs():
    assert _compute_max_speed_from_raw_rs([{"distance": 10.0}, {"distance": 20.0}]) is None
    assert _compute_max_speed_from_raw_rs([{"rs": 30.0}, {"distance": 20.0}, {"rs": 42.0}]) == 4.2


def test_compute_avg_heart_rate_returns_rounded_average():
    points = [
        {"hr": 120},
        {"hr": 131},
        {"hr": 129},
    ]

    assert _compute_avg_heart_rate(points) == 127


def test_compute_max_heart_rate_returns_max_value():
    points = [
        {"hr": 120},
        {"hr": 131},
        {"hr": 129},
    ]

    assert _compute_max_heart_rate(points) == 131


def test_compute_avg_cadence_returns_rounded_average():
    points = [
        {"s-r": 0},
        {"s-r": 160},
        {"s-r": 165},
        {"s-r": 166},
        {"s-r": -2},
    ]

    assert _compute_avg_cadence(points) == 164


def test_compute_avg_cadence_uses_time_weighted_averaging():
    """Time-weighted averaging corrects the bias from non-uniform 5-second Huawei sampling.

    When GPS dropouts or pauses cause longer intervals between cadence samples during
    high-cadence periods, a simple count-based average under-weights those periods and
    reports an average that is too low. Weighting each sample by the time until the
    next sample gives the correct time-proportional average.
    """
    # t=0ms:  160 spm → covers 5s until next sample   (weight=5000ms)
    # t=5000ms: 180 spm → covers 15s gap to next sample (weight=15000ms)
    # t=20000ms: 160 spm → last sample, default 5s weight (weight=5000ms)
    points = [
        {"timestamp": 0, "s-r": 160},
        {"timestamp": 5_000, "s-r": 180},
        {"timestamp": 20_000, "s-r": 160},
    ]
    # Simple count avg = (160+180+160)/3 = 166.7 → 167  (too low: under-weights the 15s high-cadence interval)
    # Time-weighted   = (160×5000 + 180×15000 + 160×5000) / 25000 = 172.0 → 172
    assert _compute_avg_cadence(points) == 172


def test_compute_max_cadence_ignores_invalid_values():
    points = [
        {"s-r": 0},
        {"s-r": -1},
        {"s-r": 170},
        {"s-r": 180},
        {"s-r": 300},
    ]

    assert _compute_max_cadence(points) == 180


def test_compute_avg_cadence_from_cycles_uses_time_weighted_formula():
    assert _compute_avg_cadence_from_cycles(320, 120.0) == 160
    assert _compute_avg_cadence_from_cycles(None, 120.0) is None
    assert _compute_avg_cadence_from_cycles(320, 0.0) is None


def test_compute_total_cycles_returns_none_without_cadence_samples():
    points = [
        {"total-cycles": 0.0},
        {"total-cycles": 123.0},
    ]

    from hicoros.fit.fit_writer import _compute_total_cycles

    assert _compute_total_cycles(points) is None


def test_build_distance_laps_builds_km_splits_and_tail():
    points = [
        {"timestamp": 0, "distance": 0.0},
        {"timestamp": 300000, "distance": 1000.0},
        {"timestamp": 660000, "distance": 2200.0},
    ]

    laps = _build_distance_laps(points, lap_distance_m=1000.0)

    assert len(laps) == 3
    assert laps[0]["distance"] == 1000.0
    assert laps[1]["distance"] == 1000.0
    assert laps[2]["distance"] == 200.0


def test_save_fit_file_lap_total_calories_sum_matches_session_total(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyE2EActivity:
        def __init__(self):
            self.activity_id = "dummy_activity"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(minutes=20)
            self.time_zone = None
            self.distance = 400.0
            self.calories = 500.0

            self._segments = [
                {
                    "start": self.start,
                    "stop": self.start + timedelta(minutes=5),
                    "distance": 100.0,
                },
                {
                    "start": self.start + timedelta(minutes=5),
                    "stop": self.start + timedelta(minutes=20),
                    "distance": 300.0,
                },
            ]

            self._records = [
                    {
                        "t": self.start,
                        "distance": 0.0,
                        "lat": 39.9,
                        "lon": 116.3,
                        "alti": 10.0,
                        "hr": 120,
                        "s-r": 160,
                    },
                {
                    "t": self.start + timedelta(minutes=5),
                    "distance": 100.0,
                    "lat": 39.901,
                    "lon": 116.301,
                    "alti": 15.0,
                    "hr": 130,
                        "s-r": 162,
                },
                {
                    "t": self.start + timedelta(minutes=20),
                    "distance": 400.0,
                    "lat": 39.905,
                    "lon": 116.305,
                    "alti": 20.0,
                    "hr": 140,
                        "s-r": 164,
                },
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "e2e.fit"
    save_fit_file(DummyE2EActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    session_total_calories = messages["session_mesgs"][0].get("total_calories")
    lap_total_calories_sum = sum(lap.get("total_calories", 0) for lap in messages.get("lap_mesgs", []))
    assert session_total_calories == lap_total_calories_sum
    assert messages["lap_mesgs"][0].get("avg_heart_rate") is not None
    assert messages["lap_mesgs"][0].get("max_heart_rate") is not None
    assert messages["lap_mesgs"][0].get("enhanced_avg_speed") is None
    assert messages["session_mesgs"][0].get("enhanced_avg_speed") is None
    assert messages["session_mesgs"][0].get("avg_heart_rate") is not None
    assert messages["session_mesgs"][0].get("max_heart_rate") is not None
    record_cadences = [msg.get("cadence") for msg in messages["record_mesgs"] if msg.get("cadence") is not None]
    assert 80 in record_cadences
    assert 82 in record_cadences
    assert max(record_cadences) == 82
    assert messages["lap_mesgs"][0].get("avg_cadence") == 81
    assert messages["lap_mesgs"][0].get("max_cadence") == 82
    assert messages["session_mesgs"][0].get("avg_cadence") == 81
    assert messages["session_mesgs"][0].get("max_cadence") == 82
    assert messages["session_mesgs"][0].get("total_cycles") is None
    assert messages["lap_mesgs"][0].get("total_cycles") is None
    assert all(msg.get("total_cycles") is None for msg in messages["record_mesgs"])

    first_lap = messages["lap_mesgs"][0]
    assert first_lap.get("avg_speed") is None

    session = messages["session_mesgs"][0]
    assert session.get("avg_speed") is None


def test_save_fit_file_record_speed_comes_from_pm_n_without_rs(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyPaceOnlyActivity:
        def __init__(self):
            self.activity_id = "dummy_pace_only"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(seconds=20)
            self.time_zone = None
            self.distance = 80.0
            self.calories = None

            self._segments = [
                {
                    "start": self.start,
                    "stop": self.stop,
                    "distance": 80.0,
                }
            ]

            self._records = [
                {
                    "t": self.start,
                    "distance": 0.0,
                    "lat": 39.9,
                    "lon": 116.3,
                    "pm-n": 250.0,
                },
                {
                    "t": self.start + timedelta(seconds=10),
                    "distance": 40.0,
                    "lat": 39.901,
                    "lon": 116.301,
                    "pm-n": 200.0,
                },
                {
                    "t": self.start + timedelta(seconds=20),
                    "distance": 80.0,
                    "lat": 39.902,
                    "lon": 116.302,
                    "pm-n": 160.0,
                },
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "pace_only.fit"
    save_fit_file(DummyPaceOnlyActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    record_mesgs = messages.get("record_mesgs", [])
    assert len(record_mesgs) >= 3

    speeds = [msg.get("speed") for msg in record_mesgs]
    assert speeds[0] == pytest.approx(1000.0 / 250.0, rel=1e-3)
    assert speeds[1] == pytest.approx(1000.0 / 200.0, rel=1e-3)
    assert speeds[2] == pytest.approx(1000.0 / 160.0, rel=1e-3)


def test_save_fit_file_total_cycles_not_extrapolated_without_cadence_samples(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummySparseCadenceActivity:
        def __init__(self):
            self.activity_id = "dummy_sparse_cadence"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(seconds=20)
            self.time_zone = None
            self.distance = 60.0
            self.calories = None

            self._segments = [
                {
                    "start": self.start,
                    "stop": self.stop,
                    "distance": 60.0,
                }
            ]

            self._records = [
                {
                    "t": self.start,
                    "distance": 0.0,
                    "lat": 39.9,
                    "lon": 116.3,
                    "s-r": 180,
                },
                {
                    "t": self.start + timedelta(seconds=10),
                    "distance": 30.0,
                    "lat": 39.901,
                    "lon": 116.301,
                },
                {
                    "t": self.start + timedelta(seconds=20),
                    "distance": 60.0,
                    "lat": 39.902,
                    "lon": 116.302,
                    "s-r": 180,
                },
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "sparse_cadence.fit"
    save_fit_file(DummySparseCadenceActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    record_total_cycles = [msg.get("total_cycles") for msg in messages["record_mesgs"] if msg.get("total_cycles") is not None]
    assert not record_total_cycles  # total_cycles not written to records; no spurious values


def test_save_fit_file_record_cadence_caps_for_coros_compatibility(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyHighCadenceActivity:
        def __init__(self):
            self.activity_id = "dummy_high_cadence"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(seconds=10)
            self.time_zone = None
            self.distance = 30.0
            self.calories = None

            self._segments = [
                {
                    "start": self.start,
                    "stop": self.stop,
                    "distance": 30.0,
                }
            ]

            self._records = [
                {
                    "t": self.start,
                    "distance": 0.0,
                    "lat": 39.9,
                    "lon": 116.3,
                    "s-r": 250,
                },
                {
                    "t": self.start + timedelta(seconds=5),
                    "distance": 15.0,
                    "lat": 39.901,
                    "lon": 116.301,
                    "s-r": 240,
                },
                {
                    "t": self.start + timedelta(seconds=10),
                    "distance": 30.0,
                    "lat": 39.902,
                    "lon": 116.302,
                    "s-r": 230,
                },
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "high_cadence.fit"
    save_fit_file(DummyHighCadenceActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    record_cadences = [msg.get("cadence") for msg in messages["record_mesgs"] if msg.get("cadence") is not None]
    assert record_cadences
    assert max(record_cadences) == 100


def test_save_fit_file_cycle_derived_cadence_not_above_200(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyHighCadenceActivity:
        def __init__(self):
            self.activity_id = "dummy_high_cadence_cycles"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(seconds=20)
            self.time_zone = None
            self.distance = 60.0
            self.calories = None

            self._segments = [
                {
                    "start": self.start,
                    "stop": self.stop,
                    "distance": 60.0,
                }
            ]

            self._records = [
                {
                    "t": self.start,
                    "distance": 0.0,
                    "lat": 39.9,
                    "lon": 116.3,
                    "s-r": 250,
                },
                {
                    "t": self.start + timedelta(seconds=5),
                    "distance": 15.0,
                    "lat": 39.901,
                    "lon": 116.301,
                    "s-r": 245,
                },
                {
                    "t": self.start + timedelta(seconds=10),
                    "distance": 30.0,
                    "lat": 39.902,
                    "lon": 116.302,
                    "s-r": 240,
                },
                {
                    "t": self.start + timedelta(seconds=15),
                    "distance": 45.0,
                    "lat": 39.903,
                    "lon": 116.303,
                    "s-r": 235,
                },
                {
                    "t": self.start + timedelta(seconds=20),
                    "distance": 60.0,
                    "lat": 39.904,
                    "lon": 116.304,
                    "s-r": 230,
                },
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "high_cadence_cycles.fit"
    save_fit_file(DummyHighCadenceActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    records = messages.get("record_mesgs", [])
    inferred_cadences = []
    for previous, current in zip(records, records[1:]):
        prev_ts = previous.get("timestamp")
        curr_ts = current.get("timestamp")
        prev_cycles = previous.get("total_cycles")
        curr_cycles = current.get("total_cycles")
        if not all(isinstance(value, (int, float)) for value in (prev_ts, curr_ts, prev_cycles, curr_cycles)):
            continue
        delta_ms = curr_ts - prev_ts
        delta_cycles = curr_cycles - prev_cycles
        if delta_ms <= 0 or delta_cycles < 0:
            continue
        if delta_ms > 1000:
            inferred_cadence = delta_cycles * 60000.0 / delta_ms
        else:
            inferred_cadence = delta_cycles * 60.0 / delta_ms
        inferred_cadences.append(inferred_cadence)

    # total_cycles is no longer written to records; verify cadence field is capped at 100 (s-r / 2)
    record_cadences = [msg.get("cadence") for msg in records if msg.get("cadence") is not None]
    assert record_cadences
    assert max(record_cadences) <= 100
    assert all(msg.get("total_cycles") is None for msg in records)


def test_save_fit_file_record_speed_comes_from_p_m_without_rs(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyPaceMOnlyActivity:
        def __init__(self):
            self.activity_id = "dummy_p_m_only"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(seconds=20)
            self.time_zone = None
            self.distance = 80.0
            self.calories = None

            self._segments = [
                {
                    "start": self.start,
                    "stop": self.stop,
                    "distance": 80.0,
                }
            ]

            self._records = [
                {
                    "t": self.start,
                    "distance": 0.0,
                    "lat": 39.9,
                    "lon": 116.3,
                    "p-m": 300.0,
                },
                {
                    "t": self.start + timedelta(seconds=10),
                    "distance": 40.0,
                    "lat": 39.901,
                    "lon": 116.301,
                    "p-m": 240.0,
                },
                {
                    "t": self.start + timedelta(seconds=20),
                    "distance": 80.0,
                    "lat": 39.902,
                    "lon": 116.302,
                    "p-m": 200.0,
                },
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "pace_m_only.fit"
    save_fit_file(DummyPaceMOnlyActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    record_mesgs = messages.get("record_mesgs", [])
    assert len(record_mesgs) >= 3

    speeds = [msg.get("speed") for msg in record_mesgs]
    assert speeds[0] == pytest.approx(1000.0 / 300.0, rel=1e-3)
    assert speeds[1] == pytest.approx(1000.0 / 240.0, rel=1e-3)
    assert speeds[2] == pytest.approx(1000.0 / 200.0, rel=1e-3)


def test_save_fit_file_record_speed_comes_from_r_pm_speed_without_rs(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyRealtimeSpeedActivity:
        def __init__(self):
            self.activity_id = "dummy_r_pm_speed"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(seconds=20)
            self.time_zone = None
            self.distance = 80.0
            self.calories = None

            self._segments = [{"start": self.start, "stop": self.stop, "distance": 80.0}]
            self._records = [
                {"t": self.start, "distance": 0.0, "lat": 39.9, "lon": 116.3, "r-pm-s": 7.2},
                {"t": self.start + timedelta(seconds=10), "distance": 40.0, "lat": 39.901, "lon": 116.301, "r-pm-s": 10.8},
                {"t": self.start + timedelta(seconds=20), "distance": 80.0, "lat": 39.902, "lon": 116.302, "r-pm-s": 14.4},
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "realtime_speed.fit"
    save_fit_file(DummyRealtimeSpeedActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    speeds = [msg.get("speed") for msg in messages.get("record_mesgs", [])]
    assert speeds[0] == pytest.approx(7.2 / 3.6, rel=1e-3)
    assert speeds[1] == pytest.approx(10.8 / 3.6, rel=1e-3)
    assert speeds[2] == pytest.approx(14.4 / 3.6, rel=1e-3)


def test_save_fit_file_swim_record_speed_comes_from_r_pm_pace_with_conversion(tmp_path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyRealtimePaceSwimActivity:
        def __init__(self):
            self.activity_id = "dummy_r_pm_pace_swim"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            self.stop = self.start + timedelta(seconds=20)
            self.time_zone = None
            self.distance = 80.0
            self.calories = None

            self._segments = [{"start": self.start, "stop": self.stop, "distance": 80.0}]
            self._records = [
                {"t": self.start, "distance": 0.0, "lat": 39.9, "lon": 116.3, "r-pm-p": 30.0},
                {"t": self.start + timedelta(seconds=10), "distance": 40.0, "lat": 39.901, "lon": 116.301, "r-pm-p": 24.0},
                {"t": self.start + timedelta(seconds=20), "distance": 80.0, "lat": 39.902, "lon": 116.302, "r-pm-p": 20.0},
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_POOL_SWIM

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "realtime_pace_swim.fit"
    save_fit_file(DummyRealtimePaceSwimActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    speeds = [msg.get("speed") for msg in messages.get("record_mesgs", [])]
    assert speeds[0] == pytest.approx(1000.0 / (30.0 * 10.0), rel=1e-3)
    assert speeds[1] == pytest.approx(1000.0 / (24.0 * 10.0), rel=1e-3)
    assert speeds[2] == pytest.approx(1000.0 / (20.0 * 10.0), rel=1e-3)


def test_save_fit_file_record_speed_comes_from_tp_rs_end_to_end(tmp_path: Path):
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    hitrack_name = "HiTrack_170000000017000006000001"
    hitrack_path = tmp_path / hitrack_name
    hitrack_path.write_text(
        "tp=lbs;k=0;lat=39.9042;lon=116.4074;alt=0;t=1700000000\n"
        "tp=lbs;k=1;lat=39.9043;lon=116.4075;alt=0;t=1700000010\n"
        "tp=lbs;k=2;lat=39.9044;lon=116.4076;alt=0;t=1700000025\n"
        "tp=rs;k=12;v=45\n"
        "tp=rs;k=20;v=30\n",
        encoding="utf-8",
    )

    hi_activity = HiTrackFileParser(str(hitrack_path)).parse()

    fit_path = tmp_path / "tp_rs_e2e.fit"
    save_fit_file(hi_activity, save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []
    speeds = [msg.get("speed") for msg in messages.get("record_mesgs", []) if msg.get("speed") is not None]
    assert any(speed == pytest.approx(4.5, rel=1e-3) for speed in speeds)
    assert any(speed == pytest.approx(3.0, rel=1e-3) for speed in speeds)


def test_save_fit_file_pause_events_emitted_between_segments(tmp_path):
    """Timer STOP_ALL/START events must be interleaved with records at each pause boundary
    so that FIT consumers can correctly distinguish elapsed time from moving time."""
    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    class DummyPausedActivity:
        def __init__(self):
            self.activity_id = "dummy_paused"
            self.start = datetime(2025, 1, 1, 10, 0, 0)
            # segment 1: 0-5 min, pause 5-8 min, segment 2: 8-20 min
            self.stop = self.start + timedelta(minutes=20)
            self.time_zone = None
            self.distance = 400.0
            self.calories = None

            self._segments = [
                {
                    "start": self.start,
                    "stop": self.start + timedelta(minutes=5),
                    "distance": 100.0,
                },
                {
                    "start": self.start + timedelta(minutes=8),
                    "stop": self.start + timedelta(minutes=20),
                    "distance": 300.0,
                },
            ]

            self._records = [
                {"t": self.start, "distance": 0.0, "lat": 39.9, "lon": 116.3},
                {"t": self.start + timedelta(minutes=5), "distance": 100.0, "lat": 39.901, "lon": 116.301},
                {"t": self.start + timedelta(minutes=8), "distance": 100.0, "lat": 39.902, "lon": 116.302},
                {"t": self.start + timedelta(minutes=20), "distance": 400.0, "lat": 39.905, "lon": 116.305},
            ]

        def get_activity_type(self):
            return HiActivity.TYPE_RUN

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [r for r in self._records if segment["start"] <= r["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "paused.fit"
    save_fit_file(DummyPausedActivity(), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []

    # Extract timer events in order
    timer_events = [
        (e["event"], e["event_type"])
        for e in messages.get("event_mesgs", [])
        if e.get("event") == "timer"
    ]

    # Expect: START, STOP_ALL (pause), START (resume), STOP_ALL (final)
    assert timer_events[0] == ("timer", "start"), "first event must be timer start"
    assert ("timer", "stop_all") in timer_events[1:-1], "pause STOP_ALL must appear between segments"
    assert timer_events.count(("timer", "start")) >= 2, "resume START must appear after pause"
    assert timer_events[-1] == ("timer", "stop_all"), "last event must be timer stop_all"


    garmin_fit_sdk = pytest.importorskip("garmin_fit_sdk")

    fixture_path = Path(__file__).resolve().parent / "fixtures" / "real_activity_20230204_111830.json"
    if not fixture_path.exists():
        pytest.skip(f"Regression fixture not found: {fixture_path}")

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    class FixtureActivity:
        def __init__(self, payload: dict):
            self.activity_id = payload["activity_id"]
            self.start = datetime.fromisoformat(payload["start"])
            self.stop = datetime.fromisoformat(payload["stop"])
            self.time_zone = None
            self.distance = float(payload.get("distance", 0.0))
            self.calories = payload.get("calories")
            self._activity_type = payload["activity_type"]
            self._segments = [
                {
                    "start": datetime.fromisoformat(item["start"]),
                    "stop": datetime.fromisoformat(item["stop"]),
                    "distance": float(item.get("distance", 0.0)),
                }
                for item in payload["segments"]
            ]
            self._records = [
                {
                    **{k: v for k, v in item.items() if k != "t"},
                    "t": datetime.fromisoformat(item["t"]),
                }
                for item in payload["records"]
            ]

        def get_activity_type(self):
            return self._activity_type

        def get_segments(self):
            return self._segments

        def get_segment_data(self, segment):
            return [record for record in self._records if segment["start"] <= record["t"] <= segment["stop"]]

        @staticmethod
        def _is_marker_coordinate(lat, lon):
            return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    fit_path = tmp_path / "real_fixture_20230204_111830.fit"
    save_fit_file(FixtureActivity(fixture), save_dir=str(tmp_path), fit_filename=str(fit_path))

    messages, errors = garmin_fit_sdk.Decoder(garmin_fit_sdk.Stream.from_file(str(fit_path))).read(
        convert_datetimes_to_dates=False
    )

    assert errors == []

    session = messages.get("session_mesgs", [{}])[0]
    assert session.get("avg_cadence") is not None
    assert session.get("avg_cadence") >= 70
    assert session.get("max_cadence") is not None
    assert session.get("max_cadence") >= 80
    assert session.get("total_cycles") is None  # total_cycles removed to fix Coros 300+ spm display bug

    record_cadences = [msg.get("cadence") for msg in messages.get("record_mesgs", []) if msg.get("cadence") is not None]
    assert record_cadences
    assert max(record_cadences) >= 80

    record_total_cycles = [
        msg.get("total_cycles") for msg in messages.get("record_mesgs", []) if msg.get("total_cycles") is not None
    ]
    assert not record_total_cycles  # total_cycles not written to records
