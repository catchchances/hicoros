import datetime
import math
from datetime import datetime as dts
from datetime import timedelta as dts_delta
from datetime import timezone as tz


def convert_hitrack_timestamp(hitrack_timestamp: float, timestamp_ref: datetime = None) -> datetime:
    """Converts the different timestamp formats appearing in HiTrack files to a Python datetime.

    Known formats are
    - seconds (e.g. 1516273200 or 1.5162732E9)
    - milliseconds (e.g. 1516273200000 or 1.5162732E12)
    - seconds since start of day (e.g. 43200) relative to day of activity start
    """
    timestamp_digits = int(math.log10(hitrack_timestamp))
    if timestamp_ref is not None and hitrack_timestamp < 604800:
        return dts.fromtimestamp((timestamp_ref + dts_delta(seconds=hitrack_timestamp)).timestamp(), datetime.UTC)
    elif timestamp_digits == 9:
        return dts.fromtimestamp(hitrack_timestamp, datetime.UTC)

    divisor = 10 ** (timestamp_digits - 9) if timestamp_digits > 9 else 0.1 ** (9 - timestamp_digits)
    return dts.fromtimestamp(hitrack_timestamp / divisor, datetime.UTC)


def get_tz_aware_datetime(naive_datetime: dts, time_zone: tz):
    """Return timezone-aware datetime from stored UTC naive datetime and activity timezone."""
    utc_datetime = dts.replace(naive_datetime, tzinfo=tz.utc)
    if time_zone:
        return utc_datetime.astimezone(time_zone)
    return utc_datetime
