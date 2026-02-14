from dataclasses import dataclass
from pathlib import Path


@dataclass
class FitSelfCheckReport:
    fit_filename: str
    integrity_ok: bool
    warnings: list[str]
    errors: list[str]
    message_counts: dict[str, int]


REQUIRED_MESSAGE_GROUPS = ("file_id_mesgs", "session_mesgs", "activity_mesgs", "record_mesgs")


def _count_messages(messages: dict) -> dict[str, int]:
    counts = {}
    for key, value in messages.items():
        counts[key] = len(value) if isinstance(value, list) else 0
    return counts


def _add_sanity_warnings(messages: dict, warnings: list[str]):
    for group in REQUIRED_MESSAGE_GROUPS:
        if len(messages.get(group, [])) == 0:
            warnings.append(f"Missing expected message group: {group}")

    file_ids = messages.get("file_id_mesgs", [])
    if file_ids:
        file_type = file_ids[0].get("type")
        if file_type not in ("activity", 4, None):
            warnings.append(f"file_id.type is {file_type!r}, expected 'activity'.")

    activities = messages.get("activity_mesgs", [])
    sessions = messages.get("session_mesgs", [])
    if activities and sessions:
        expected_sessions = activities[0].get("num_sessions")
        if isinstance(expected_sessions, int) and expected_sessions != len(sessions):
            warnings.append(
                f"activity.num_sessions={expected_sessions} but decoded session count is {len(sessions)}."
            )

    event_messages = messages.get("event_mesgs", [])
    has_timer_start = False
    has_timer_stop = False
    for event_message in event_messages:
        event_name = event_message.get("event")
        event_type = event_message.get("event_type")
        if event_name in ("timer",):
            if event_type in ("start",):
                has_timer_start = True
            if event_type in ("stop_all", "stop"):
                has_timer_stop = True
    if not has_timer_start:
        warnings.append("No timer start event found in event messages.")
    if not has_timer_stop:
        warnings.append("No timer stop event found in event messages.")

    records = messages.get("record_mesgs", [])
    prev_timestamp = None
    prev_distance = None
    for index, record in enumerate(records):
        timestamp = record.get("timestamp")
        if isinstance(timestamp, (int, float)):
            if prev_timestamp is not None and timestamp < prev_timestamp:
                warnings.append(f"record timestamp decreases at index {index}.")
                break
            prev_timestamp = timestamp

        distance = record.get("distance")
        if isinstance(distance, (int, float)):
            if prev_distance is not None and distance + 1e-6 < prev_distance:
                warnings.append(f"record distance decreases at index {index}.")
                break
            prev_distance = distance

    cadence_groups = ("record_mesgs", "lap_mesgs", "session_mesgs")
    dual_field_hits: list[str] = []
    for group in cadence_groups:
        for index, message in enumerate(messages.get(group, [])):
            cadence = message.get("cadence")
            fractional_cadence = message.get("fractional_cadence")
            if isinstance(cadence, (int, float)) and isinstance(fractional_cadence, (int, float)):
                dual_field_hits.append(f"{group}[{index}]")

    if dual_field_hits:
        hit_preview = ", ".join(dual_field_hits[:3])
        hit_suffix = "" if len(dual_field_hits) <= 3 else f" (+{len(dual_field_hits) - 3} more)"
        warnings.append(
            "cadence and fractional_cadence are both present in the same message(s): "
            f"{hit_preview}{hit_suffix}. Some importers may sum these fields and inflate cadence readings."
        )

    cadence_values = [
        float(record["cadence"])
        for record in records
        if isinstance(record.get("cadence"), (int, float)) and float(record["cadence"]) >= 0
    ]
    if len(cadence_values) >= 5:
        doubled_like_count = sum(1 for value in cadence_values if 300 <= value <= 400)
        doubled_like_ratio = doubled_like_count / len(cadence_values)
        if doubled_like_count >= 5 and doubled_like_ratio >= 0.3:
            session_avg_cadence = None
            sessions = messages.get("session_mesgs", [])
            if sessions and isinstance(sessions[0].get("avg_cadence"), (int, float)):
                session_avg_cadence = float(sessions[0].get("avg_cadence"))

            mismatch_text = ""
            if session_avg_cadence is not None and 100 <= session_avg_cadence <= 220:
                mismatch_text = f" session.avg_cadence={session_avg_cadence:.0f} appears normal but record cadence is doubled-like."

            warnings.append(
                "Suspicious cadence doubling pattern detected: "
                f"{doubled_like_count}/{len(cadence_values)} record cadence samples are in 300-400 spm.{mismatch_text} "
                "Before importing, consider cadence downgrade processing for record samples (cadence = cadence / 2)."
            )


def check_fit_file(fit_filename: str) -> FitSelfCheckReport:
    if not Path(fit_filename).exists():
        raise FileNotFoundError(f"FIT file not found: {fit_filename}")

    try:
        from garmin_fit_sdk import Decoder
        from garmin_fit_sdk import Stream
    except ImportError as e:
        raise RuntimeError("garmin-fit-sdk is required for FIT self-check") from e

    warnings: list[str] = []
    errors: list[str] = []

    integrity_stream = Stream.from_file(fit_filename)
    integrity_ok = Decoder(integrity_stream).check_integrity()
    if not integrity_ok:
        errors.append("FIT check_integrity failed.")

    decode_stream = Stream.from_file(fit_filename)
    messages, decode_errors = Decoder(decode_stream).read(convert_datetimes_to_dates=False)
    for decode_error in decode_errors:
        warnings.append(f"Decoder warning: {decode_error}")

    _add_sanity_warnings(messages, warnings)

    return FitSelfCheckReport(
        fit_filename=fit_filename,
        integrity_ok=integrity_ok,
        warnings=warnings,
        errors=errors,
        message_counts=_count_messages(messages),
    )
