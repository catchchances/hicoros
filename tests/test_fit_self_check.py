import sys
from types import SimpleNamespace

import pytest

from hicoros.fit.fit_self_check import check_fit_file


class _FakeStream:
    @staticmethod
    def from_file(filename):
        return filename


def _install_fake_sdk(monkeypatch, *, integrity_ok=True, messages=None, decode_errors=None):
    if messages is None:
        messages = {
            "file_id_mesgs": [{"type": "activity"}],
            "session_mesgs": [{"total_distance": 1000}],
            "activity_mesgs": [{"num_sessions": 1}],
            "event_mesgs": [
                {"event": "timer", "event_type": "start"},
                {"event": "timer", "event_type": "stop_all"},
            ],
            "record_mesgs": [
                {"timestamp": 1, "distance": 0},
                {"timestamp": 2, "distance": 10},
            ],
        }
    if decode_errors is None:
        decode_errors = []

    class _FakeDecoder:
        def __init__(self, _stream):
            self._stream = _stream

        def check_integrity(self):
            return integrity_ok

        def read(self, convert_datetimes_to_dates=False):
            return messages, decode_errors

    fake_module = SimpleNamespace(Decoder=_FakeDecoder, Stream=_FakeStream)
    monkeypatch.setitem(sys.modules, "garmin_fit_sdk", fake_module)


def test_check_fit_file_reports_ok(tmp_path, monkeypatch):
    fit_file = tmp_path / "ok.fit"
    fit_file.write_bytes(b"FIT")

    _install_fake_sdk(monkeypatch)

    report = check_fit_file(str(fit_file))

    assert report.integrity_ok is True
    assert report.errors == []
    assert report.warnings == []
    assert report.message_counts["record_mesgs"] == 2


def test_check_fit_file_reports_integrity_and_sanity_warnings(tmp_path, monkeypatch):
    fit_file = tmp_path / "bad.fit"
    fit_file.write_bytes(b"FIT")

    messages = {
        "file_id_mesgs": [{"type": "course"}],
        "session_mesgs": [{"total_distance": 1000}],
        "activity_mesgs": [{"num_sessions": 2}],
        "event_mesgs": [{"event": "timer", "event_type": "start"}],
        "record_mesgs": [
            {"timestamp": 2, "distance": 10},
            {"timestamp": 1, "distance": 9},
        ],
    }

    _install_fake_sdk(monkeypatch, integrity_ok=False, messages=messages, decode_errors=["decode warning"])

    report = check_fit_file(str(fit_file))

    assert report.integrity_ok is False
    assert any("check_integrity failed" in err for err in report.errors)
    assert any("Decoder warning" in warn for warn in report.warnings)
    assert any("file_id.type" in warn for warn in report.warnings)
    assert any("num_sessions" in warn for warn in report.warnings)
    assert any("No timer stop event" in warn for warn in report.warnings)
    assert any("record timestamp decreases" in warn for warn in report.warnings)


def test_check_fit_file_warns_on_dual_cadence_fields(tmp_path, monkeypatch):
    fit_file = tmp_path / "dual_cadence.fit"
    fit_file.write_bytes(b"FIT")

    messages = {
        "file_id_mesgs": [{"type": "activity"}],
        "session_mesgs": [{"total_distance": 1000}],
        "activity_mesgs": [{"num_sessions": 1}],
        "event_mesgs": [
            {"event": "timer", "event_type": "start"},
            {"event": "timer", "event_type": "stop_all"},
        ],
        "record_mesgs": [
            {"timestamp": 1, "distance": 0, "cadence": 176, "fractional_cadence": 0.5},
            {"timestamp": 2, "distance": 10, "cadence": 175},
        ],
    }

    _install_fake_sdk(monkeypatch, integrity_ok=True, messages=messages, decode_errors=[])

    report = check_fit_file(str(fit_file))

    assert any("cadence and fractional_cadence are both present" in warn for warn in report.warnings)


def test_check_fit_file_warns_on_suspicious_doubled_cadence_pattern(tmp_path, monkeypatch):
    fit_file = tmp_path / "doubled_cadence.fit"
    fit_file.write_bytes(b"FIT")

    messages = {
        "file_id_mesgs": [{"type": "activity"}],
        "session_mesgs": [{"total_distance": 1000, "avg_cadence": 172}],
        "activity_mesgs": [{"num_sessions": 1}],
        "event_mesgs": [
            {"event": "timer", "event_type": "start"},
            {"event": "timer", "event_type": "stop_all"},
        ],
        "record_mesgs": [
            {"timestamp": 1, "distance": 0, "cadence": 340},
            {"timestamp": 2, "distance": 10, "cadence": 345},
            {"timestamp": 3, "distance": 20, "cadence": 350},
            {"timestamp": 4, "distance": 30, "cadence": 355},
            {"timestamp": 5, "distance": 40, "cadence": 360},
            {"timestamp": 6, "distance": 50, "cadence": 170},
        ],
    }

    _install_fake_sdk(monkeypatch, integrity_ok=True, messages=messages, decode_errors=[])

    report = check_fit_file(str(fit_file))

    assert any("Suspicious cadence doubling pattern detected" in warn for warn in report.warnings)
    assert any("cadence = cadence / 2" in warn for warn in report.warnings)


def test_check_fit_file_does_not_warn_on_normal_cadence_pattern(tmp_path, monkeypatch):
    fit_file = tmp_path / "normal_cadence.fit"
    fit_file.write_bytes(b"FIT")

    messages = {
        "file_id_mesgs": [{"type": "activity"}],
        "session_mesgs": [{"total_distance": 1000, "avg_cadence": 171}],
        "activity_mesgs": [{"num_sessions": 1}],
        "event_mesgs": [
            {"event": "timer", "event_type": "start"},
            {"event": "timer", "event_type": "stop_all"},
        ],
        "record_mesgs": [
            {"timestamp": 1, "distance": 0, "cadence": 166},
            {"timestamp": 2, "distance": 10, "cadence": 170},
            {"timestamp": 3, "distance": 20, "cadence": 174},
            {"timestamp": 4, "distance": 30, "cadence": 171},
            {"timestamp": 5, "distance": 40, "cadence": 169},
            {"timestamp": 6, "distance": 50, "cadence": 172},
        ],
    }

    _install_fake_sdk(monkeypatch, integrity_ok=True, messages=messages, decode_errors=[])

    report = check_fit_file(str(fit_file))

    assert not any("Suspicious cadence doubling pattern detected" in warn for warn in report.warnings)


def test_check_fit_file_raises_for_missing_file(tmp_path):
    missing = tmp_path / "missing.fit"
    with pytest.raises(FileNotFoundError):
        check_fit_file(str(missing))
