import logging
import os
from datetime import datetime, timezone

from hicoros.constants import OUTPUT_DIR
from hicoros.constants import PROGRAM_NAME
from hicoros.hi.hi_activity import HiActivity
from hicoros.time_utils import get_tz_aware_datetime


def build_fit_filename(output_dir: str, hi_activity: HiActivity) -> str:
    return "%s/HiTrack_%s.fit" % (
        output_dir,
        get_tz_aware_datetime(hi_activity.start, hi_activity.time_zone).strftime("%Y%m%d_%H%M%S"),
    )


def _to_epoch_millis(ts: datetime) -> int:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return round(ts.timestamp() * 1000)


def _enum_value(enum_cls, *names, default=None):
    if enum_cls is None:
        return default
    for name in names:
        if hasattr(enum_cls, name):
            return getattr(enum_cls, name)
    return default


def _resolve_sport(hi_activity: HiActivity, sport_enum):
    activity_type = hi_activity.get_activity_type()
    if activity_type == HiActivity.TYPE_CYCLE or activity_type == HiActivity.TYPE_INDOOR_CYCLE:
        return _enum_value(sport_enum, "CYCLING", default=None)
    if activity_type == HiActivity.TYPE_WALK:
        return _enum_value(sport_enum, "WALKING", default=None)
    if activity_type in (HiActivity.TYPE_POOL_SWIM, HiActivity.TYPE_OPEN_WATER_SWIM):
        return _enum_value(sport_enum, "SWIMMING", default=None)
    if activity_type in (HiActivity.TYPE_HIKE, HiActivity.TYPE_MOUNTAIN_HIKE):
        return _enum_value(sport_enum, "HIKING", default=None)
    return _enum_value(sport_enum, "RUNNING", default=None)



def _compute_summary_values(
    default_start_ts: int,
    default_stop_ts: int,
    default_elapsed: float,
    default_distance: float,
    first_lap_start_ts: int | None,
    last_lap_stop_ts: int | None,
    lap_total_timer: float,
    lap_total_distance: float,
    first_record_ts: int | None,
    last_record_ts: int | None,
    last_record_distance: float | None,
):
    summary_start_ts = default_start_ts
    summary_stop_ts = default_stop_ts

    if first_lap_start_ts is not None:
        summary_start_ts = first_lap_start_ts
    elif first_record_ts is not None:
        summary_start_ts = min(summary_start_ts, first_record_ts)

    if last_lap_stop_ts is not None:
        summary_stop_ts = last_lap_stop_ts
    elif last_record_ts is not None:
        summary_stop_ts = max(summary_stop_ts, last_record_ts)

    summary_timer = lap_total_timer if lap_total_timer > 0 else max(default_elapsed, 0.0)

    if lap_total_distance > 0:
        summary_distance = lap_total_distance
    elif last_record_distance is not None and last_record_distance >= 0:
        summary_distance = last_record_distance
    else:
        summary_distance = max(default_distance, 0.0)

    window_elapsed = max((summary_stop_ts - summary_start_ts) / 1000.0, 0.0)
    summary_elapsed = max(window_elapsed, summary_timer, max(default_elapsed, 0.0))

    return summary_start_ts, summary_stop_ts, summary_elapsed, summary_timer, summary_distance


def _compute_altitude_gain_loss(points: list[dict]) -> tuple[float, float]:
    total_ascent = 0.0
    total_descent = 0.0
    previous_altitude = None

    for point in points:
        altitude = point.get("alti")
        if not isinstance(altitude, (int, float)):
            continue
        altitude = float(altitude)
        if previous_altitude is not None:
            delta = altitude - previous_altitude
            if delta > 0:
                total_ascent += delta
            elif delta < 0:
                total_descent += -delta
        previous_altitude = altitude

    return total_ascent, total_descent


def _compute_total_calories(hi_activity: HiActivity) -> int | None:
    if hi_activity.calories is None:
        return None
    if not isinstance(hi_activity.calories, (int, float)):
        return None
    if hi_activity.calories <= 0:
        return None
    return int(round(hi_activity.calories))


def _distribute_calories_by_distance(total_calories: int, lap_distances: list[float]) -> list[int] | None:
    if total_calories <= 0:
        return None
    if not lap_distances:
        return None

    normalized = [max(float(distance), 0.0) for distance in lap_distances]
    distance_sum = sum(normalized)
    if distance_sum <= 0:
        return None

    raw_shares = [total_calories * distance / distance_sum for distance in normalized]
    allocated = [int(share) for share in raw_shares]
    remainder = total_calories - sum(allocated)

    remainders = sorted(
        range(len(raw_shares)),
        key=lambda idx: (raw_shares[idx] - allocated[idx]),
        reverse=True,
    )
    for idx in remainders[:remainder]:
        allocated[idx] += 1

    return allocated


def _derive_record_speed(data: dict, previous_point: dict | None, allow_distance_fallback: bool = True) -> float | None:
    if isinstance(data.get("r-pm-s"), (int, float)):
        return max(float(data["r-pm-s"]) / 3.6, 0.0)

    if isinstance(data.get("r-pm-p"), (int, float)):
        pace_seconds = float(data["r-pm-p"])
        if pace_seconds > 0:
            return 1000.0 / pace_seconds

    if isinstance(data.get("rs"), (int, float)):
        return max(float(data["rs"]) / 10.0, 0.0)

    if isinstance(data.get("pm-n"), (int, float)):
        pace_seconds = float(data["pm-n"])
        if pace_seconds > 0:
            return 1000.0 / pace_seconds

    if isinstance(data.get("p-m"), (int, float)):
        pace_seconds = float(data["p-m"])
        if pace_seconds > 0:
            return 1000.0 / pace_seconds

    if not allow_distance_fallback:
        return None

    if (
        previous_point is None
        or not isinstance(data.get("distance"), (int, float))
        or not isinstance(previous_point.get("distance"), (int, float))
    ):
        return None

    delta_time_seconds = (data["timestamp"] - previous_point["timestamp"]) / 1000.0
    delta_distance = float(data["distance"]) - float(previous_point["distance"])
    if delta_time_seconds <= 0 or delta_distance < 0:
        return None
    return delta_distance / delta_time_seconds


def _derive_record_speed_from_raw_rs(data: dict) -> float | None:
    if isinstance(data.get("r-pm-s"), (int, float)):
        return max(float(data["r-pm-s"]) / 3.6, 0.0)
    if isinstance(data.get("r-pm-p"), (int, float)):
        pace_seconds = float(data["r-pm-p"])
        if pace_seconds > 0:
            return 1000.0 / pace_seconds
    if isinstance(data.get("rs"), (int, float)):
        return max(float(data["rs"]) / 10.0, 0.0)
    if isinstance(data.get("pm-n"), (int, float)):
        pace_seconds = float(data["pm-n"])
        if pace_seconds > 0:
            return 1000.0 / pace_seconds
    if isinstance(data.get("p-m"), (int, float)):
        pace_seconds = float(data["p-m"])
        if pace_seconds > 0:
            return 1000.0 / pace_seconds
    return None


def _compute_max_speed_from_raw_rs(points: list[dict]) -> float | None:
    raw_speeds = []
    for point in points:
        speed = _derive_record_speed_from_raw_rs(point)
        if speed is not None:
            raw_speeds.append(speed)
    if not raw_speeds:
        return None
    return max(raw_speeds)


def _compute_speed_stats(points: list[dict], allow_distance_fallback: bool = True) -> tuple[float | None, float | None]:
    if len(points) < 2:
        return None, None

    speed_samples: list[float] = []
    previous_point = None
    for point in points:
        speed = _derive_record_speed(point, previous_point, allow_distance_fallback=allow_distance_fallback)
        if speed is not None:
            speed_samples.append(speed)
        previous_point = point

    if not speed_samples:
        return None, None

    max_speed = max(speed_samples)

    first = points[0]
    last = points[-1]
    if isinstance(first.get("distance"), (int, float)) and isinstance(last.get("distance"), (int, float)):
        distance_delta = float(last["distance"]) - float(first["distance"])
        time_delta = (last["timestamp"] - first["timestamp"]) / 1000.0
        if distance_delta >= 0 and time_delta > 0:
            return distance_delta / time_delta, max_speed

    return sum(speed_samples) / len(speed_samples), max_speed


def _compute_avg_heart_rate(points: list[dict]) -> int | None:
    heart_rates = [int(point["hr"]) for point in points if isinstance(point.get("hr"), (int, float))]
    if not heart_rates:
        return None
    return int(round(sum(heart_rates) / len(heart_rates)))


def _compute_max_heart_rate(points: list[dict]) -> int | None:
    heart_rates = [int(point["hr"]) for point in points if isinstance(point.get("hr"), (int, float))]
    if not heart_rates:
        return None
    return max(heart_rates)


def _compute_avg_cadence(points: list[dict]) -> int | None:
    # Collect (timestamp, cadence) pairs for valid cadence samples
    samples = [
        (point.get("timestamp"), int(point["s-r"]))
        for point in points
        if isinstance(point.get("s-r"), (int, float)) and 0 < float(point["s-r"]) <= 255
    ]
    if not samples:
        return None

    # Use time-weighted averaging when timestamps are available.
    # Each sample is weighted by the interval until the next sample, so that
    # longer gaps between samples (e.g. due to 5-second Huawei sampling with GPS
    # dropouts) are correctly represented rather than being under-weighted.
    if all(isinstance(ts, (int, float)) for ts, _ in samples):
        samples_sorted = sorted(samples, key=lambda x: x[0])
        total_weight = 0.0
        weighted_sum = 0.0
        for i, (ts, cad) in enumerate(samples_sorted):
            if i < len(samples_sorted) - 1:
                weight = float(samples_sorted[i + 1][0] - ts)
            else:
                weight = 5000.0  # default 5-second weight for the last sample
            weight = max(weight, 1.0)  # ensure positive weight for duplicate timestamps
            weighted_sum += cad * weight
            total_weight += weight
        if total_weight > 0:
            return int(round(weighted_sum / total_weight))

    # Fallback: simple average when timestamps are unavailable
    cadence_values = [cad for _, cad in samples]
    return int(round(sum(cadence_values) / len(cadence_values)))


def _compute_max_cadence(points: list[dict]) -> int | None:
    cadence_values = [
        int(point["s-r"])
        for point in points
        if isinstance(point.get("s-r"), (int, float)) and 0 < float(point["s-r"]) <= 255
    ]
    if not cadence_values:
        return None
    return max(cadence_values)


def _compute_total_cycles(points: list[dict]) -> int | None:
    if not points:
        return None

    has_cadence_samples = any(
        isinstance(point.get("s-r"), (int, float)) and 0 <= float(point["s-r"]) <= 255 for point in points
    )
    if not has_cadence_samples:
        return None

    cycle_values = [
        float(point["total-cycles"])
        for point in points
        if isinstance(point.get("total-cycles"), (int, float)) and float(point["total-cycles"]) >= 0
    ]
    if not cycle_values:
        return None

    total_cycles = max(cycle_values) - min(cycle_values)
    if total_cycles < 0:
        return None
    return int(round(total_cycles))


def _compute_avg_cadence_from_cycles(total_cycles: int | None, elapsed_seconds: float) -> int | None:
    if total_cycles is None:
        return None
    if elapsed_seconds <= 0:
        return None
    return int(round(total_cycles * 60.0 / elapsed_seconds))


def _build_distance_laps(record_points: list[dict], lap_distance_m: float = 1000.0) -> list[dict]:
    valid = [point for point in record_points if isinstance(point.get("distance"), (int, float))]
    if len(valid) < 2:
        return []

    first = valid[0]
    current_lap_start_ts = first["timestamp"]
    current_lap_start_distance = float(first["distance"])

    next_lap_end_distance = (int(current_lap_start_distance // lap_distance_m) + 1) * lap_distance_m
    laps: list[dict] = []

    previous = first
    for current in valid[1:]:
        if current["timestamp"] <= previous["timestamp"]:
            previous = current
            continue
        if float(current["distance"]) < float(previous["distance"]):
            previous = current
            continue

        while float(current["distance"]) >= next_lap_end_distance:
            span_distance = float(current["distance"]) - float(previous["distance"])
            if span_distance <= 0:
                break

            ratio = (next_lap_end_distance - float(previous["distance"])) / span_distance
            lap_stop_ts = int(round(previous["timestamp"] + ratio * (current["timestamp"] - previous["timestamp"])))

            laps.append(
                {
                    "start_ts": current_lap_start_ts,
                    "stop_ts": lap_stop_ts,
                    "distance": next_lap_end_distance - current_lap_start_distance,
                }
            )

            current_lap_start_ts = lap_stop_ts
            current_lap_start_distance = next_lap_end_distance
            next_lap_end_distance += lap_distance_m

        previous = current

    last = valid[-1]
    tail_distance = float(last["distance"]) - current_lap_start_distance
    if tail_distance > 0 and last["timestamp"] > current_lap_start_ts:
        laps.append({"start_ts": current_lap_start_ts, "stop_ts": last["timestamp"], "distance": tail_distance})

    return laps


def _slice_points_by_timestamp(points: list[dict], start_ts: int, stop_ts: int) -> list[dict]:
    return [point for point in points if start_ts <= point["timestamp"] <= stop_ts]


def _build_fit_file(hi_activity: HiActivity):
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.profile_type import Activity
    from fit_tool.profile.messages.activity_message import ActivityMessage
    from fit_tool.profile.messages.event_message import EventMessage
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.lap_message import LapMessage
    from fit_tool.profile.messages.record_message import RecordMessage
    from fit_tool.profile.messages.session_message import SessionMessage
    from fit_tool.profile.profile_type import Event
    from fit_tool.profile.profile_type import EventType
    from fit_tool.profile.profile_type import FileType
    from fit_tool.profile.profile_type import Manufacturer
    from fit_tool.profile.profile_type import Sport

    start_ts = _to_epoch_millis(hi_activity.start)
    stop_ts = _to_epoch_millis(hi_activity.stop)
    total_elapsed = max((hi_activity.stop - hi_activity.start).total_seconds(), 0)
    sport = _resolve_sport(hi_activity, Sport)
    is_swim_activity = hi_activity.get_activity_type() in (HiActivity.TYPE_POOL_SWIM, HiActivity.TYPE_OPEN_WATER_SWIM)

    builder = FitFileBuilder(auto_define=True, min_string_size=50)

    file_id = FileIdMessage()
    file_id.type = _enum_value(FileType, "ACTIVITY", default=None)
    manufacturer = _enum_value(Manufacturer, "DEVELOPMENT", default=0)
    if hasattr(manufacturer, "value"):
        manufacturer = manufacturer.value
    file_id.manufacturer = manufacturer
    file_id.product = 0
    file_id.serial_number = 0
    file_id.time_created = start_ts
    builder.add(file_id)

    start_event = EventMessage()
    start_event.event = _enum_value(Event, "TIMER", default=None)
    start_event.event_type = _enum_value(EventType, "START", default=None)
    start_event.timestamp = start_ts
    builder.add(start_event)

    first_position = None
    last_position = None
    first_record_ts = None
    last_record_ts = None
    last_record_distance = None
    total_ascent = 0.0
    total_descent = 0.0
    record_points: list[dict] = []
    previous_point = None
    previous_export_cadence = None
    previous_export_cadence_timestamp = None
    cadence_hold_ms = 5_000
    valid_segments = [seg for seg in hi_activity.get_segments() if seg.get("start") and seg.get("stop")]
    for seg_idx, segment in enumerate(valid_segments):
        segment_records = []
        for data in hi_activity.get_segment_data(segment):
            if "t" not in data:
                continue
            record = RecordMessage()
            record_ts = _to_epoch_millis(data["t"])
            record.timestamp = record_ts
            if first_record_ts is None:
                first_record_ts = record_ts
            last_record_ts = record_ts

            if "distance" in data:
                record_distance = float(data["distance"])
                record.distance = record_distance
                last_record_distance = record_distance
            if "hr" in data:
                record.heart_rate = int(data["hr"])
            cadence_value = None
            export_cadence_value = None
            if isinstance(data.get("s-r"), (int, float)) and 0 <= float(data["s-r"]) <= 255:
                cadence_value = int(data["s-r"])
                export_cadence_value = min(int(round(cadence_value / 2.0)), 100)
                previous_export_cadence = export_cadence_value
                previous_export_cadence_timestamp = record_ts
            elif previous_export_cadence is not None and previous_export_cadence_timestamp is not None:
                export_delta_ms = record_ts - previous_export_cadence_timestamp
                if 0 < export_delta_ms <= cadence_hold_ms:
                    export_cadence_value = previous_export_cadence

            if export_cadence_value is not None:
                record.cadence = export_cadence_value

            if "lat" in data and "lon" in data and not hi_activity._is_marker_coordinate(data["lat"], data["lon"]):
                record.position_lat = float(data["lat"])
                record.position_long = float(data["lon"])
                if first_position is None:
                    first_position = (float(data["lat"]), float(data["lon"]))
                last_position = (float(data["lat"]), float(data["lon"]))
            if "alti" in data:
                record.altitude = float(data["alti"])

            point = {
                "timestamp": record_ts,
                "distance": float(data["distance"]) if isinstance(data.get("distance"), (int, float)) else None,
                "alti": float(data["alti"]) if isinstance(data.get("alti"), (int, float)) else None,
                "rs": float(data["rs"]) if isinstance(data.get("rs"), (int, float)) else None,
                "r-pm-s": float(data["r-pm-s"]) if isinstance(data.get("r-pm-s"), (int, float)) else None,
                "r-pm-p": float(data["r-pm-p"]) * 10.0
                if is_swim_activity and isinstance(data.get("r-pm-p"), (int, float))
                else float(data["r-pm-p"])
                if isinstance(data.get("r-pm-p"), (int, float))
                else None,
                "pm-n": float(data["pm-n"]) if isinstance(data.get("pm-n"), (int, float)) else None,
                "p-m": float(data["p-m"]) if isinstance(data.get("p-m"), (int, float)) else None,
                "hr": int(data["hr"]) if isinstance(data.get("hr"), (int, float)) else None,
                "s-r": int(data["s-r"]) if isinstance(data.get("s-r"), (int, float)) else None,
                "total-cycles": None,
            }

            point_speed = _derive_record_speed_from_raw_rs(point)
            if point_speed is not None:
                record.speed = point_speed

            record_points.append(point)
            previous_point = point
            segment_records.append(record)

        if segment_records:
            builder.add_all(segment_records)

        # Emit timer STOP_ALL (pause) / START (resume) events between segments so that
        # FIT consumers (Garmin Connect, Strava, Coros, etc.) correctly attribute elapsed
        # time during pauses to stopped time rather than moving time.
        if seg_idx < len(valid_segments) - 1:
            next_segment = valid_segments[seg_idx + 1]

            pause_event = EventMessage()
            pause_event.event = _enum_value(Event, "TIMER", default=None)
            pause_event.event_type = _enum_value(EventType, "STOP_ALL", default=None)
            pause_event.timestamp = _to_epoch_millis(segment["stop"])
            builder.add(pause_event)

            resume_event = EventMessage()
            resume_event.event = _enum_value(Event, "TIMER", default=None)
            resume_event.event_type = _enum_value(EventType, "START", default=None)
            resume_event.timestamp = _to_epoch_millis(next_segment["start"])
            builder.add(resume_event)

    calories_total = _compute_total_calories(hi_activity)

    laps: list[tuple[object, float]] = []
    generated_distance_laps = _build_distance_laps(record_points, lap_distance_m=1000.0)

    lap_total_timer = 0.0
    lap_total_distance = 0.0
    first_lap_start_ts = None
    last_lap_stop_ts = None

    if generated_distance_laps:
        for generated_lap in generated_distance_laps:
            lap_start = generated_lap["start_ts"]
            lap_stop = generated_lap["stop_ts"]
            lap_distance = float(generated_lap["distance"])
            lap_elapsed = max((lap_stop - lap_start) / 1000.0, 0.0)

            lap_points = _slice_points_by_timestamp(record_points, lap_start, lap_stop)
            lap_ascent, lap_descent = _compute_altitude_gain_loss(lap_points)
            lap_avg_speed, _ = _compute_speed_stats(lap_points, allow_distance_fallback=False)
            lap_max_speed = _compute_max_speed_from_raw_rs(lap_points)
            lap_avg_heart_rate = _compute_avg_heart_rate(lap_points)
            lap_max_heart_rate = _compute_max_heart_rate(lap_points)
            lap_max_cadence = _compute_max_cadence(lap_points)
            if lap_max_cadence is not None:
                lap_max_cadence = min(int(round(lap_max_cadence / 2.0)), 100)
            lap_avg_cadence_raw = _compute_avg_cadence(lap_points)
            lap_avg_cadence = min(int(round(lap_avg_cadence_raw / 2.0)), 100) if lap_avg_cadence_raw is not None else None
            total_ascent += lap_ascent
            total_descent += lap_descent

            lap = LapMessage()
            lap.timestamp = lap_stop
            lap.start_time = lap_start
            lap.total_elapsed_time = lap_elapsed
            lap.total_timer_time = lap_elapsed
            lap.total_distance = lap_distance
            lap.total_ascent = lap_ascent
            lap.total_descent = lap_descent
            if lap_avg_speed is not None:
                lap.avg_speed = lap_avg_speed
                lap.enhanced_avg_speed = lap_avg_speed
            if lap_max_speed is not None:
                lap.max_speed = lap_max_speed
                lap.enhanced_max_speed = lap_max_speed
            if lap_avg_heart_rate is not None:
                lap.avg_heart_rate = lap_avg_heart_rate
            if lap_max_heart_rate is not None:
                lap.max_heart_rate = lap_max_heart_rate
            if lap_avg_cadence is not None:
                lap.avg_cadence = lap_avg_cadence
            if lap_max_cadence is not None:
                lap.max_cadence = lap_max_cadence
            if sport is not None:
                lap.sport = sport
            if first_position:
                lap.start_position_lat = first_position[0]
                lap.start_position_long = first_position[1]
            if last_position:
                lap.end_position_lat = last_position[0]
                lap.end_position_long = last_position[1]

            if first_lap_start_ts is None:
                first_lap_start_ts = lap_start
            last_lap_stop_ts = lap_stop
            lap_total_timer += lap_elapsed
            lap_total_distance += lap_distance

            laps.append((lap, lap_distance))
    else:
        for segment in hi_activity.get_segments():
            if not segment.get("start") or not segment.get("stop"):
                continue

            segment_data = hi_activity.get_segment_data(segment)
            lap_ascent, lap_descent = _compute_altitude_gain_loss(segment_data)
            segment_points = [
                {
                    "timestamp": _to_epoch_millis(data["t"]),
                    "distance": data.get("distance"),
                    "alti": data.get("alti"),
                    "rs": data.get("rs"),
                    "r-pm-s": data.get("r-pm-s"),
                    "r-pm-p": (data.get("r-pm-p") * 10.0)
                    if is_swim_activity and isinstance(data.get("r-pm-p"), (int, float))
                    else data.get("r-pm-p"),
                    "pm-n": data.get("pm-n"),
                    "p-m": data.get("p-m"),
                    "hr": data.get("hr"),
                    "s-r": data.get("s-r"),
                }
                for data in segment_data
                if "t" in data
            ]
            lap_avg_speed, _ = _compute_speed_stats(segment_points, allow_distance_fallback=False)
            lap_max_speed = _compute_max_speed_from_raw_rs(segment_points)
            lap_avg_heart_rate = _compute_avg_heart_rate(segment_points)
            lap_max_heart_rate = _compute_max_heart_rate(segment_points)
            lap_max_cadence = _compute_max_cadence(segment_points)
            if lap_max_cadence is not None:
                lap_max_cadence = min(int(round(lap_max_cadence / 2.0)), 100)
            total_ascent += lap_ascent
            total_descent += lap_descent

            lap = LapMessage()
            lap_start = _to_epoch_millis(segment["start"])
            lap_stop = _to_epoch_millis(segment["stop"])
            lap_elapsed = max((segment["stop"] - segment["start"]).total_seconds(), 0)
            lap_distance = float(segment.get("distance", 0))
            lap_avg_cadence_raw = _compute_avg_cadence(segment_points)
            lap_avg_cadence = min(int(round(lap_avg_cadence_raw / 2.0)), 100) if lap_avg_cadence_raw is not None else None

            if first_lap_start_ts is None:
                first_lap_start_ts = lap_start
            last_lap_stop_ts = lap_stop
            lap_total_timer += lap_elapsed
            lap_total_distance += lap_distance

            lap.timestamp = lap_stop
            lap.start_time = lap_start
            lap.total_elapsed_time = lap_elapsed
            lap.total_timer_time = lap_elapsed
            lap.total_distance = lap_distance
            lap.total_ascent = lap_ascent
            lap.total_descent = lap_descent
            if lap_avg_speed is not None:
                lap.avg_speed = lap_avg_speed
                lap.enhanced_avg_speed = lap_avg_speed
            if lap_max_speed is not None:
                lap.max_speed = lap_max_speed
                lap.enhanced_max_speed = lap_max_speed
            if lap_avg_heart_rate is not None:
                lap.avg_heart_rate = lap_avg_heart_rate
            if lap_max_heart_rate is not None:
                lap.max_heart_rate = lap_max_heart_rate
            if lap_avg_cadence is not None:
                lap.avg_cadence = lap_avg_cadence
            if lap_max_cadence is not None:
                lap.max_cadence = lap_max_cadence
            if sport is not None:
                lap.sport = sport
            if first_position:
                lap.start_position_lat = first_position[0]
                lap.start_position_long = first_position[1]
            if last_position:
                lap.end_position_lat = last_position[0]
                lap.end_position_long = last_position[1]

            laps.append((lap, lap_distance))

    summary_start_ts, summary_stop_ts, summary_elapsed, summary_timer, summary_distance = _compute_summary_values(
        default_start_ts=start_ts,
        default_stop_ts=stop_ts,
        default_elapsed=total_elapsed,
        default_distance=float(max(hi_activity.distance, 0)),
        first_lap_start_ts=first_lap_start_ts,
        last_lap_stop_ts=last_lap_stop_ts,
        lap_total_timer=lap_total_timer,
        lap_total_distance=lap_total_distance,
        first_record_ts=first_record_ts,
        last_record_ts=last_record_ts,
        last_record_distance=last_record_distance,
    )

    lap_calories = None
    if calories_total is not None:
        lap_calories = _distribute_calories_by_distance(calories_total, [lap_distance for _, lap_distance in laps])

    for index, (lap, _lap_distance) in enumerate(laps):
        if lap_calories is not None:
            lap.total_calories = lap_calories[index]
        builder.add(lap)

    session = SessionMessage()
    session.timestamp = summary_stop_ts
    session.start_time = summary_start_ts
    session.total_elapsed_time = summary_elapsed
    session.total_timer_time = summary_timer
    session.total_distance = summary_distance
    session.total_ascent = total_ascent
    session.total_descent = total_descent
    session_avg_heart_rate = _compute_avg_heart_rate(record_points)
    session_max_heart_rate = _compute_max_heart_rate(record_points)
    session_max_cadence = _compute_max_cadence(record_points)
    if session_max_cadence is not None:
        session_max_cadence = min(int(round(session_max_cadence / 2.0)), 100)
    session_avg_cadence_raw = _compute_avg_cadence(record_points)
    session_avg_cadence = min(int(round(session_avg_cadence_raw / 2.0)), 100) if session_avg_cadence_raw is not None else None
    session_avg_speed, _ = _compute_speed_stats(record_points, allow_distance_fallback=False)
    session_max_speed = _compute_max_speed_from_raw_rs(record_points)
    if session_avg_heart_rate is not None:
        session.avg_heart_rate = session_avg_heart_rate
    if session_max_heart_rate is not None:
        session.max_heart_rate = session_max_heart_rate
    if session_avg_cadence is not None:
        session.avg_cadence = session_avg_cadence
    if session_max_cadence is not None:
        session.max_cadence = session_max_cadence
    if session_avg_speed is not None:
        session.avg_speed = session_avg_speed
        session.enhanced_avg_speed = session_avg_speed
    if session_max_speed is not None:
        session.max_speed = session_max_speed
        session.enhanced_max_speed = session_max_speed
    if calories_total is not None:
        session.total_calories = calories_total
    if sport is not None:
        session.sport = sport
    if first_position:
        session.start_position_lat = first_position[0]
        session.start_position_long = first_position[1]
    if last_position:
        session.end_position_lat = last_position[0]
        session.end_position_long = last_position[1]
    builder.add(session)

    stop_event = EventMessage()
    stop_event.event = _enum_value(Event, "TIMER", default=None)
    stop_event.event_type = _enum_value(EventType, "STOP_ALL", default=None)
    stop_event.timestamp = summary_stop_ts
    builder.add(stop_event)

    activity = ActivityMessage()
    activity.event = _enum_value(Event, "ACTIVITY", default=None)
    activity.event_type = _enum_value(EventType, "STOP", default=None)
    activity.timestamp = summary_stop_ts
    activity.total_timer_time = summary_timer
    activity.num_sessions = 1
    activity.type = _enum_value(Activity, "MANUAL", default=None)
    builder.add(activity)

    return builder.build()


def _validate_fit(fit_filename: str):
    from garmin_fit_sdk import Decoder
    from garmin_fit_sdk import Stream

    stream = Stream.from_file(fit_filename)
    decoder = Decoder(stream)
    if not decoder.check_integrity():
        raise RuntimeError(f"Generated FIT failed integrity check: {fit_filename}")


def save_fit_file(
    hi_activity: HiActivity,
    save_dir: str = OUTPUT_DIR,
    filename_prefix: str = None,
    fit_filename: str = None,
) -> str:
    if not hi_activity:
        logging.getLogger(PROGRAM_NAME).error("No valid HiTrack activity specified to construct FIT activity.")
        raise Exception("No valid HiTrack activity specified to construct FIT activity.")

    fit_file = _build_fit_file(hi_activity)

    if not fit_filename:
        fit_filename = save_dir + "/"
        if filename_prefix:
            fit_filename += datetime.strftime(hi_activity.start, filename_prefix)
        fit_filename += hi_activity.activity_id
        fit_filename += ".fit"

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    logging.getLogger(PROGRAM_NAME).info(
        "Saving FIT file <%s> for HiTrack activity <%s>", fit_filename, hi_activity.activity_id
    )
    fit_file.to_file(fit_filename)
    _validate_fit(fit_filename)
    return fit_filename
