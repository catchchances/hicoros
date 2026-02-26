import collections
import datetime
import logging
import operator
from datetime import datetime as dts_delta_datetime
from datetime import timedelta as dts_delta
from typing import Optional

from hicoros.constants import GPS_TIMEOUT
from hicoros.constants import PROGRAM_NAME
from hicoros.time_utils import convert_hitrack_timestamp
from hicoros import _vincenty as vincenty_ext


vincenty_distance_batch_m = vincenty_ext.vincenty_distance_batch_m
gcj02_to_wgs84_batch = vincenty_ext.gcj02_to_wgs84_batch


class HiActivity:
    """This class represents all the data contained in a HiTrack file."""

    TYPE_WALK = "Walk"
    TYPE_RUN = "Run"
    TYPE_CYCLE = "Cycle"
    TYPE_POOL_SWIM = "Swim_Pool"
    TYPE_OPEN_WATER_SWIM = "Swim_Open_Water"
    TYPE_HIKE = "Hike"
    TYPE_MOUNTAIN_HIKE = "Mountain_Hike"
    TYPE_INDOOR_RUN = "Indoor_Run"
    TYPE_INDOOR_CYCLE = "Indoor_Cycle"
    TYPE_CROSS_TRAINER = "Cross_Trainer"
    TYPE_OTHER = "Other"
    TYPE_CROSSFIT = ("CrossFit",)
    TYPE_CROSS_COUNTRY_RUN = "Cross_Country_Run"
    TYPE_UNKNOWN = "?"

    _ACTIVITY_TYPE_LIST = (
        TYPE_WALK,
        TYPE_RUN,
        TYPE_CYCLE,
        TYPE_POOL_SWIM,
        TYPE_OPEN_WATER_SWIM,
        TYPE_HIKE,
        TYPE_MOUNTAIN_HIKE,
        TYPE_INDOOR_RUN,
        TYPE_INDOOR_CYCLE,
        TYPE_CROSS_TRAINER,
        TYPE_OTHER,
        TYPE_CROSSFIT,
        TYPE_CROSS_COUNTRY_RUN,
    )

    def __init__(
        self,
        activity_id: str,
        activity_type: str = TYPE_UNKNOWN,
        timestamp_ref: datetime.datetime = None,
        start_timestamp_ref: datetime.datetime = None,
    ):
        logging.getLogger(PROGRAM_NAME).debug("New HiTrack activity to process <%s>", activity_id)
        self.activity_id = activity_id

        if activity_type == self.TYPE_UNKNOWN:
            self._activity_type = self.TYPE_UNKNOWN
        else:
            self.set_activity_type(activity_type)  # validate and set activity type of the activity

        # Will hold a set of parameters to auto-determine activity type
        self.activity_params = {}

        self.pool_length = -1

        # All date and timestamp variables are stored as time zone unaware because there is no time zone information
        # available in the raw HiTrack files. However, time zone information is available from the JSON data and can be
        # stored as an attribute of the HiActivity (see below). Please take care to properly format any display/output
        # dates and times using this time zone information.
        self.start = None
        self.stop = None
        self.time_zone = None
        # Huawei Health provided distance or in absence the calculated distance derived from GPS data.
        self.distance = -1
        # Calculated distance derived from GPS data may differ from Huawei Health recorded distance
        self.calculated_distance = -1
        self.calories = -1

        # Create an empty segment and segment list
        self._current_segment = None
        self._segment_list = None

        # Create an empty detail data dictionary. key = timestamp, value = dict{t, lat, lon, alt, hr)
        self.data_dict = {}

        # Create an empty list for the (pool) swim data
        self.swim_data = []

        # Private variable to temporarily hold the last parsed SWOLF data during parsing of swimming activities
        self.last_swolf_data = None

        self.timestamp_ref = timestamp_ref
        self.start_timestamp_ref = start_timestamp_ref

    @classmethod
    def from_json_pool_swim_data(cls, activity_id: str, start: datetime.datetime, json_pool_swim_dict):
        """Create a HiActivity from the swim data in the JSON file.
        Uses the data in the mSwimSegments section of the JSON file (lap distance, duration, swolf)
        """
        if json_pool_swim_dict is None or len(json_pool_swim_dict) == 0:
            logging.getLogger(PROGRAM_NAME).warning(
                "Swimming activity %s is empty (no segment data) and can not be " + "instantiated.", activity_id
            )
            return

        swim_activity = cls(activity_id, HiActivity.TYPE_POOL_SWIM)
        swim_activity.start = start

        # Parse lap data
        swim_activity.calculated_distance = 0
        lap_start = start
        for swim_segment in json_pool_swim_dict:
            # Create lap
            lap_distance = int(swim_segment["mDistance"])
            lap_duration = int(swim_segment["mDuration"])
            lap_stop = lap_start + dts_delta(seconds=lap_duration)
            lap_data = {
                "lap": int(swim_segment["mSegmentIndex"]),
                "start": lap_start,
                "stop": lap_stop,
                "duration": lap_duration,
                "distance": lap_distance,
                "swolf": int(swim_segment["mSwolf"]),
                "strokes": int(swim_segment["mPullTimes"]),
            }

            swim_activity.swim_data.append(lap_data)
            swim_activity._add_segment_start(lap_start)
            swim_activity._add_segment_stop(lap_stop, lap_distance)
            swim_activity.calculated_distance += lap_distance
            swim_activity.stop = lap_stop
            lap_start = lap_stop

        return swim_activity

    @classmethod
    def from_manual_json_pool_swim_data(
        cls, activity_id: str, start: datetime.datetime, duration_millis: int, distance: int
    ):
        swim_activity = cls(activity_id, HiActivity.TYPE_POOL_SWIM)
        swim_activity.start = start
        swim_activity.stop = start + dts_delta(milliseconds=duration_millis)
        swim_activity.calculated_distance = distance
        lap_data = {
            "lap": 1,
            "start": swim_activity.start,
            "stop": swim_activity.stop,
            "duration": duration_millis / 1000,
            "distance": distance,
            "swolf": 0,
            "strokes": 0,
        }
        swim_activity.swim_data.append(lap_data)

        return swim_activity

    def get_activity_type(self) -> str:
        if self._activity_type == self.TYPE_UNKNOWN:
            # Perform activity type detection only once.
            self._activity_type = self._detect_activity_type()
        return self._activity_type

    def set_activity_type(self, activity_type: str):
        if activity_type in self._ACTIVITY_TYPE_LIST:
            logging.getLogger(PROGRAM_NAME).info(
                "Setting activity type of activity %s to %s", self.activity_id, activity_type
            )
            self._activity_type = activity_type
        else:
            logging.getLogger(PROGRAM_NAME).error("Invalid activity type <%s>", activity_type)
            raise Exception("Invalid activity type <%s>", activity_type)

    def set_pool_length(self, pool_length: int):
        logging.getLogger(PROGRAM_NAME).info("Setting pool length of activity %s to %d", self.activity_id, pool_length)
        self.pool_length = pool_length
        if not self.get_activity_type() == self.TYPE_POOL_SWIM:
            logging.getLogger(PROGRAM_NAME).warning(
                "Pool length for activity %s of type %s will not be used. It is not a pool swimming activity",
                self.activity_id,
                self._activity_type,
            )

    def _add_segment_start(self, segment_start: datetime.datetime):
        if self._current_segment:
            logging.getLogger(PROGRAM_NAME).error(
                "Request to start segment at %s when there is already a current segment active", segment_start
            )
            return

        logging.getLogger(PROGRAM_NAME).debug("Adding segment start at %s", segment_start)

        # No current segment, create one
        self._current_segment = {"start": segment_start, "stop": None}
        # Add it to the segment list (note: if no explicit stop record is found, the segment will exist and stay 'open')
        if not self._segment_list:
            self._segment_list = []
        self._segment_list.append(self._current_segment)
        if not self.start:
            # Set activity start
            self.start = segment_start

    def _add_segment_stop(self, segment_stop: datetime.datetime, segment_distance: int = -1):
        logging.getLogger(PROGRAM_NAME).debug("Adding segment stop at %s", segment_stop)
        if not self._current_segment:
            logging.getLogger(PROGRAM_NAME).error(
                "Request to stop segment at %s when there is no current segment active", segment_stop
            )
            return

        # Set stop of current segment, add it to the segment list and clear the current segment
        self._current_segment["stop"] = segment_stop
        self._current_segment["duration"] = int((segment_stop - self._current_segment["start"]).total_seconds())
        if not segment_distance == -1:
            self._current_segment["distance"] = segment_distance
        else:
            self._current_segment["distance"] = 0

        self._current_segment = None

    @staticmethod
    def _is_marker_coordinate(lat: float, lon: float) -> bool:
        return (lat == 90 and lon == -80) or (lat == 0 and lon == 0)

    # TODO Verify if something useful can be done with the (optional) altitude data in the tp=lbs records
    def add_location_data(self, data: list[list[str]]):
        self.add_location_data_batch([data])

    def add_location_data_batch(self, data_batch: list[list[list[str]]]):
        """Add location data from a tp=lbs record in the HiTrack file.
        Information:
        - When tracking an activity with a mobile phone only, the HiTrack files seem to contain altitude
          information in the alt data tag (in ft). This seems not to be the case when an activity is started from a
          tracking device.
        - When tracking an activity with a mobile phone only, the HiTrack files seem to contain stop records (see below)
          with a valid timestamp. This is not the case when a tracking device is used, where the timestamp of these
          records = 0
        - When tracking an activity with a tracking the device, the records in the HiTrack file seem to be ordered by
          record type. This seems not to be the case when using a mobile phone only, where records seem to be added in
          order of the timestamp they occurred.
        - Location records are NOT ordered by timestamp when the activity contains loops of the same track.
        - Pause and stop records are identified by tp=lbs;lat=90;lon=-80;alt=0;t=<valid epoch time value or zero>
        """

        logging.getLogger(PROGRAM_NAME).debug("Adding location data batch with %d records", len(data_batch))

        location_data_batch = []
        gcj_points = []
        gcj_point_indexes = []

        for data in data_batch:
            # Create a dictionary from the key value pairs
            location_data = dict(data)

            # All raw values are floats (timestamp will be converted later)
            for keys in location_data:
                location_data[keys] = float(location_data[keys])

            # Keep raw tp=lbs index under a dedicated key for traceability/debugging.
            if "k" in location_data:
                location_data["lbs-k"] = location_data.pop("k")

            if location_data["t"] == 0 and location_data["lat"] == 90 and location_data["lon"] == -80:
                # Pause/stop record without a valid epoch timestamp. Set it to the last timestamp recorded
                location_data["t"] = self.stop
            elif location_data["t"] == 0 and location_data["lat"] == 0 and location_data["lon"] == 0:
                # Exception (Guess) - this type of record seems to be generated once at the start of the activtiy when no GPS data is available.
                # Set the start timestamp (only possible in case of json or zip conversion).
                logging.getLogger(PROGRAM_NAME).debug(
                    "Found zero location record. Setting activity start to reference %s", self.start_timestamp_ref
                )
                self.start = self.start_timestamp_ref
            else:
                # Regular location record or pause/stop record with valid epoch timestamp or seconds since start of day.
                # Convert the timestamp to a datetime
                location_data["t"] = convert_hitrack_timestamp(location_data["t"], timestamp_ref=self.timestamp_ref)

                # Convert regular GCJ-02 coordinates to WGS84 using batched conversion.
                # Keep pause/stop marker coordinates untouched.
                if not self._is_marker_coordinate(location_data["lat"], location_data["lon"]):
                    gcj_points.append((location_data["lat"], location_data["lon"]))
                    gcj_point_indexes.append(len(location_data_batch))

                self.activity_params["gps"] = True

            location_data_batch.append(location_data)

        if gcj_points:
            converted_points = gcj02_to_wgs84_batch(gcj_points)
            for index, converted in zip(gcj_point_indexes, converted_points):
                location_data_batch[index]["lat"], location_data_batch[index]["lon"] = converted

        # Only add location data with a valid timestamp (ignore GPS loss or pause records at start of the location data)
        for location_data in location_data_batch:
            if location_data["t"]:
                self._add_data_detail(location_data)

    def _get_last_location(self) -> Optional[dict]:
        """Returns the last location record in the data dictionary"""
        if self.data_dict:
            reverse_sorted_data = sorted(self.data_dict.items(), key=operator.itemgetter(0), reverse=True)
            for t, data in reverse_sorted_data:
                if "lat" in data:
                    return data
        # Empty data dictionary or no last location found in dictionary
        return None

    def add_heart_rate_data(self, data: list[list[str]]):
        """Add heart rate data from a tp=h-r record in the HiTrack file.
        Time value k is interpreted as minutes since activity start.
        """
        # Create a dictionary from the key value pairs
        logging.getLogger(PROGRAM_NAME).debug("Adding heart rate data %s", data)

        hr_data = dict(data)

        # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored heart rate record at relative time <%s> before first record with absolute time.",
                hr_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> hr
        # Legacy format: k is minutes since activity start.
        # Newer format: k can be an absolute epoch timestamp (seconds or milliseconds).
        heart_rate_time_value = float(hr_data.pop("k"))
        if heart_rate_time_value >= 10_000_000:
            hr_data["t"] = convert_hitrack_timestamp(heart_rate_time_value, timestamp_ref=self.timestamp_ref)
        else:
            hr_data["t"] = self.start + dts_delta(seconds=heart_rate_time_value * 60)
        hr_data["hr"] = int(hr_data.pop("v"))

        # Ignore invalid heart rate data (for export)
        if hr_data["hr"] < 1 or hr_data["hr"] > 254:
            logging.getLogger(PROGRAM_NAME).warning("Invalid heart rate data detected and ignored in data %s", data)

        # Add heart rate data
        self._add_data_detail(hr_data)

    def add_altitude_data(self, data: list[list[str]]):
        """Add altitude data from a tp=alt or tp=alti record in a HiTrack file.

        Time value k is interpreted as seconds since activity start.
        The first record with k=0 is the value registered after 5 seconds of activity.
        """
        # Create a dictionary from the key value pairs
        logging.getLogger(PROGRAM_NAME).debug("Adding altitude data %s", data)

        alti_data = dict(data)

        # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored altitude record at relative time <%s> before first record with absolute time.",
                alti_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> alti
        # Legacy format: k is seconds since activity start with first sample at +5s.
        # Newer format: k can be an absolute epoch timestamp (seconds or milliseconds).
        altitude_time_value = float(alti_data.pop("k"))
        if altitude_time_value >= 10_000_000:
            alti_data["t"] = convert_hitrack_timestamp(altitude_time_value, timestamp_ref=self.timestamp_ref)
        else:
            alti_data["t"] = self.start + dts_delta(seconds=altitude_time_value + 5)
        alti_data["alti"] = float(alti_data.pop("v"))

        # Ignore invalid altitude data
        if alti_data["alti"] < -1000 or alti_data["alti"] > 10000:
            logging.getLogger(PROGRAM_NAME).warning("Invalid altitude data detected and ignored in data %s", data)
            return

        # Add altitude data
        self._add_data_detail(alti_data)

    # TODO Further verification of assumptions and testing required related to auto activity type detection
    # TODO For activities that were tracked using a phone only without a fitness device, there are no s-r records. Hence, in these cases auto detection should use a 'fallback mode' e.g. by using the p-m records (and assume that swimming activities with phone only won't occur)
    def add_step_frequency_data(self, data: list[list[str]]):
        """Add step frequency data from a tp=s-r record in a HiTrack file.
        The unit of measure of the step frequency is steps/minute.
                Time value k is interpreted as minutes since activity start.
         Assumptions:
         - Cycling activities have s-r records with value = 0 (and Huawei/Honor doesn't seem to sell cadence meters)
         - Swimming activities have s-r records but no lbs records. The s-r records have negative values
           (indicating the stroke type). It seems that s-r records are used to indicate
           the start of a new segments for swimming.
        """

        logging.getLogger(PROGRAM_NAME).debug(
            "Adding step frequency data or detecting cycling or swimming activities %s", data
        )

        # Create a dictionary from the key value pairs
        step_freq_data = dict(data)

        # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored step frequency record at relative time <%s> before first record with absolute time.",
                step_freq_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> s_r
        # Legacy format: k is minutes since activity start.
        # Newer format: k can be an absolute epoch timestamp (seconds or milliseconds).
        step_frequency_time_value = float(step_freq_data.pop("k"))
        if step_frequency_time_value >= 10_000_000:
            step_freq_data["t"] = convert_hitrack_timestamp(step_frequency_time_value, timestamp_ref=self.timestamp_ref)
        else:
            step_freq_data["t"] = self.start + dts_delta(seconds=step_frequency_time_value * 60)
        step_freq_data["s-r"] = int(step_freq_data.pop("v"))

        # Keep track of minimum, maximum and average step frequency data for activity type auto-detection.
        # Ignore negative values since these belong to swimming activities and are not important to recognize the
        # swimming activity.
        if step_freq_data["s-r"] >= 0:
            if "step frequency min" not in self.activity_params:
                self.activity_params["step frequency min"] = step_freq_data["s-r"]
                self.activity_params["step frequency max"] = step_freq_data["s-r"]
                self.activity_params["step frequency data"] = []
            elif step_freq_data["s-r"] < self.activity_params["step frequency min"]:
                self.activity_params["step frequency min"] = step_freq_data["s-r"]
            elif step_freq_data["s-r"] > self.activity_params["step frequency max"]:
                self.activity_params["step frequency max"] = step_freq_data["s-r"]

            # Add step frequency data detail to activity parameters for later average step frequency calculation.
            self.activity_params["step frequency data"].append(step_freq_data["s-r"])

        # Add step frequency data.
        self._add_data_detail(step_freq_data)

    def add_swolf_data(self, data: list[list[str]]):
        """Add SWOLF (swimming) data from a tp=swf record in a HiTrack file
        SWOLF value = time to swim one pool length + number of strokes
        """

        logging.getLogger(PROGRAM_NAME).debug("Adding SWOLF swim data %s", data)

        # Create a dictionary from the key value pairs
        swolf_data = dict(data)

        # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored SWOLF record at relative time <%s> before first " + "record with absolute time.",
                swolf_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> swf
        # Time of SWOLF swimming data is relative to activity start.
        # The first record with k=0 is the value registered after 5 seconds of activity.
        swolf_data["t"] = self.start + dts_delta(seconds=int(swolf_data.pop("k")) + 5)
        swolf_data["swf"] = int(swolf_data.pop("v"))

        self.activity_params["swim"] = True

        # If there is no last swf record or the last added swf record had a different swf value, then this record
        # belongs to a new lap (segment)
        # TODO There is a chance that checking on SWOLF only might miss a lap in case two consecutive laps have the same SWOLF (but then again, chances are that stroke and speed data are also identical)
        # TODO Since SWOLF value contains both time and strokes, add extra check to not process consecutive same time laps beyond the SWOLF value.
        if not self._current_segment:
            # First record of first lap. Start new segment (lap)
            self._add_segment_start(swolf_data["t"] - dts_delta(seconds=5))
        else:
            if self.last_swolf_data["swf"] != swolf_data["swf"]:
                # New lap detected.
                # Close segment of previous lap. Since the current lap starts at the exact same time
                self._current_segment["stop"] = self.last_swolf_data["t"]
                self._current_segment = None
                # Open new segment for this lap. End of previous lap is start of current lap.
                # Add 1 microsecond to split the lap data correctly.
                self._add_segment_start(swolf_data["t"] + dts_delta(microseconds=1))

        # Remember this SWOLF data as last parsed SWOLF data.
        self.last_swolf_data = swolf_data

        # Add SWOLF data
        self._add_data_detail(swolf_data)

    def add_stroke_frequency_data(self, data: list[list[str]]):
        """Add stroke frequency (swimming) data (in strokes/minute) from a tp=p-f record in a HiTrack file"""

        logging.getLogger(PROGRAM_NAME).debug("Adding stroke frequency swim data %s", data)

        # Create a dictionary from the key value pairs
        stroke_freq_data = dict(data)

        # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored stroke frequency record at relative time <%s> " + "before first record with absolute time.",
                stroke_freq_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> p-f
        # Time of stroke frequency swimming data is relative to activity start.
        # The first record with k=0 is the value registered after 5 seconds of activity.
        stroke_freq_data["t"] = self.start + dts_delta(seconds=int(stroke_freq_data.pop("k")) + 5)
        stroke_freq_data["p-f"] = int(stroke_freq_data.pop("v"))

        # Add stroke frequency data
        self._add_data_detail(stroke_freq_data)

    def add_speed_data(self, data: list[list[str]]):
        """Add real-time speed data from a tp=rs record in a HiTrack file.

        Time value k is interpreted as exercise time in seconds since activity start.
        Value v is real-time speed in decimeter/second.
        """

        logging.getLogger(PROGRAM_NAME).debug("Adding speed data %s", data)

        # Create a dictionary from the key value pairs
        speed_data = dict(data)

        # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored speed record at relative time <%s> before " + "first record with absolute time.",
                speed_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> rs
        # Time of speed data is relative to activity start in seconds.
        speed_data["t"] = self.start + dts_delta(seconds=float(speed_data.pop("k")))
        speed_data["rs"] = float(speed_data.pop("v"))

        # Ignore invalid speed data records (negative speed value, e.g. for indoor (cycling) activities)
        if speed_data["rs"] < 0:
            return

        # Add speed data
        self._add_data_detail(speed_data)

    def add_interval_pace_data(self, data: list[list[str]]):
        """Add interval pace data (metric) from a tp=pm-n record in a HiTrack file.

        Time value k is interpreted as interval index.
        Each index represents a 5-second interval since activity start.
        Value v is pace in seconds.
        """

        logging.getLogger(PROGRAM_NAME).debug("Adding interval pace data %s", data)

        pace_data = dict(data)

        # Ignore records (with relative timestamp/index) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored interval pace record at index <%s> before first record with absolute time.",
                pace_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> pm-n
        pace_index = int(float(pace_data.pop("k")))
        pace_data["t"] = self.start + dts_delta(seconds=pace_index * 5 + 5)
        pace_data["pm-n"] = float(pace_data.pop("v"))

        # Ignore invalid pace data
        if pace_data["pm-n"] < 0:
            logging.getLogger(PROGRAM_NAME).warning("Invalid interval pace data detected and ignored in data %s", data)
            return

        self._add_data_detail(pace_data)

    def add_pace_data(self, data: list[list[str]]):
        """Add pace data from a tp=p-m record in a HiTrack file.

        Time value k is interpreted as index value.
        Each index represents a 5-second interval since activity start.
        Value v is pace in seconds.
        """

        logging.getLogger(PROGRAM_NAME).debug("Adding pace data %s", data)

        pace_data = dict(data)

        # Ignore records (with relative timestamp/index) before at least 1 record with an absolute timestamp is processed.
        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored pace record at index <%s> before first record with absolute time.",
                pace_data.pop("k"),
            )
            return

        # Use unique keys. Update keys k -> t and v -> p-m
        pace_index = int(float(pace_data.pop("k")))
        pace_data["t"] = self.start + dts_delta(seconds=pace_index * 5 + 5)
        pace_data["p-m"] = float(pace_data.pop("v"))

        # Ignore invalid pace data
        if pace_data["p-m"] < 0:
            logging.getLogger(PROGRAM_NAME).warning("Invalid pace data detected and ignored in data %s", data)
            return

        self._add_data_detail(pace_data)

    def add_realtime_speed_pace_data(self, data: list[list[str]]):
        """Add real-time speed and pace data from a tp=r-pm record in a HiTrack file.

        Time value k is interpreted as exercise time in seconds since activity start.
        Value s is real-time speed in km/h.
        Value P is real-time pace in seconds/km.
        """

        logging.getLogger(PROGRAM_NAME).debug("Adding real-time speed and pace data %s", data)

        realtime_data = dict(data)

        if not self.start:
            logging.getLogger(PROGRAM_NAME).warning(
                "Ignored real-time speed and pace record at time <%s> before first record with absolute time.",
                realtime_data.pop("k"),
            )
            return

        realtime_data["t"] = self.start + dts_delta(seconds=float(realtime_data.pop("k")))

        if "s" in realtime_data:
            realtime_data["r-pm-s"] = float(realtime_data.pop("s"))

        pace_key = "P" if "P" in realtime_data else "p" if "p" in realtime_data else None
        if pace_key:
            realtime_data["r-pm-p"] = float(realtime_data.pop(pace_key))

        if "r-pm-s" in realtime_data and realtime_data["r-pm-s"] < 0:
            logging.getLogger(PROGRAM_NAME).warning(
                "Invalid real-time speed data detected and ignored in data %s", data
            )
            return

        if "r-pm-p" in realtime_data and realtime_data["r-pm-p"] < 0:
            logging.getLogger(PROGRAM_NAME).warning(
                "Invalid real-time pace data detected and ignored in data %s", data
            )
            return

        self._add_data_detail(realtime_data)

    def _add_data_detail(self, data: dict):
        # Add the data to the data dictionary.
        if data["t"] not in self.data_dict:
            # No data for timestamp. Create a new record for it.
            self.data_dict[data["t"]] = data
        else:
            # Existing data for timestamp. Add the new data to the existing record.
            self.data_dict[data["t"]].update(data)

        # Records are NOT necessarily in chronological order.
        # Update start of the activity when a record with an earlier timestamp is added.
        if not self.start or self.start > data["t"]:
            self.start = data["t"]
        # Update stop of the activity when a record with a later timestamp is added.
        if not self.stop or self.stop < data["t"]:
            self.stop = data["t"]

    def get_segments(self) -> list:
        """Returns the segment list.
        - For pool swimming activities, the segments were identified during parsing of the SWOLF data.
        - For walking, running and cycling activities, the segments must be calculated once based on the parsed
          location data. Because the location data is not (always) in chronological order (e.g. loops in the track),
          for these activities
        """
        # Make sure calculation of segments is done.
        self._calc_segments_and_distances()
        return self._segment_list

    def _reset_segments(self):
        self._segment_list = None
        self._current_segment = None

    def _detect_activity_type(self) -> str:
        """Auto-detection of the activity type. Only valid when called after all data has been parsed."""
        logging.getLogger(PROGRAM_NAME).debug(
            "Detecting activity type for activity %s with parameters %s", self.activity_id, self.activity_params
        )

        # Filter out swimming
        if "swim" in self.activity_params:
            # Swimming detected
            if "gps" not in self.activity_params:
                self._activity_type = self.TYPE_POOL_SWIM
            else:
                self._activity_type = self.TYPE_OPEN_WATER_SWIM
            logging.getLogger(PROGRAM_NAME).debug(
                "Activity type %s detected for activity %s", self._activity_type, self.activity_id
            )
            return self._activity_type

        # Walk / Run / Cycle
        if "step frequency min" in self.activity_params:
            # Walk / Run / Cycle - Step frequency data available
            # For walking and running, the assumption is that step frequency data is available regardless whether
            # a fitness tracking device is used or not.

            # Calculate average step frequency
            step_freq_sum = 0
            for n, step_freq in enumerate(self.activity_params["step frequency data"]):
                step_freq_sum += step_freq

            step_freq_avg = step_freq_sum / (n + 1)
            logging.getLogger(PROGRAM_NAME).debug(
                "Activity %s has a calculated average step frequency of %d", self.activity_id, step_freq_avg
            )

            if self.activity_params["step frequency min"] == 0 and self.activity_params["step frequency max"] == 0:
                # Specific check for cycling - all step frequency records being zero
                self._activity_type = self.TYPE_CYCLE
            elif self.activity_params["step frequency min"] == 0 and step_freq_avg < 70:
                # TODO This condition will have to be confirmed in practice whether a long pause during walking would cause it to be detected as cycling

                # Some walking on foot during cycling activity - detect it as cycling
                # See https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5435734/ - Figure 2 extrapolated theoretical stride
                # frequency of 35 at speed 0.
                self._activity_type = self.TYPE_CYCLE
            elif self.activity_params["step frequency max"] < 135:
                # See https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5435734/ - Walk-to-run stride frequency of 70.6 +- 3.2
                self._activity_type = self.TYPE_WALK
            else:
                self._activity_type = self.TYPE_RUN

            logging.getLogger(PROGRAM_NAME).debug(
                "Activity type %s detected using step frequency data for activity %s",
                self._activity_type,
                self.activity_id,
            )
            return self._activity_type
        else:
            # Walk / Run / Cycle - no step frequency data available (e.g. activities registered using phone only).
            # See above, since it is assumed that walking or running activities will always have step frequency records
            # regardless whether a fitness tracking device was used or not, this must be a cycling activity.
            self._activity_type = self.TYPE_CYCLE
            logging.getLogger(PROGRAM_NAME).debug(
                "Activity type %s detected using step frequency data for activity %s",
                self._activity_type,
                self.activity_id,
            )
            return self._activity_type

    def _calc_segments_and_distances(self):
        """Perform the following detailed data calculations for walk, run, or cycle activities:
        - segment list
        - segment start, stop, duration and cumulative distance
        - detailed track point cumulative distances
        - total distance

        Calculations change/add the following class attributes in place:
        - _segment_list
        - data_dict : sorted by timestamp and distances added
        - distance
        """

        # Calculate only once
        if self._segment_list:
            return

        logging.getLogger(PROGRAM_NAME).debug("Calculating segment and distance data for activity %s", self.activity_id)

        # Sort the data dictionary by timestamp
        self.data_dict = collections.OrderedDict(sorted(self.data_dict.items()))

        # Pre-calculate all required Vincenty distances in one C++ call to reduce Python<->C++ round-trips.
        distance_pairs = []
        pre_last_location = None
        for data in self.data_dict.values():
            if "lat" in data:
                if pre_last_location:
                    if data["lat"] == 90 and data["lon"] == -80:
                        continue
                    if "lat" not in pre_last_location:
                        pre_last_location = data
                    else:
                        distance_pairs.append(
                            (pre_last_location["lat"], pre_last_location["lon"], data["lat"], data["lon"])
                        )
                        pre_last_location = data
                else:
                    pre_last_location = data
            elif "rs" in data and self._activity_type != HiActivity.TYPE_OPEN_WATER_SWIM:
                if pre_last_location:
                    time_delta = data["t"] - pre_last_location["t"]
                    if "lat" not in pre_last_location or time_delta > GPS_TIMEOUT:
                        pre_last_location = data
                else:
                    pre_last_location = data

        batched_distances = vincenty_distance_batch_m(distance_pairs) if distance_pairs else []
        if len(batched_distances) != len(distance_pairs):
            raise RuntimeError("vincenty_distance_batch_m returned unexpected number of distances")
        batched_distance_index = 0

        # Do calculations
        last_location = None
        paused = False
        segment_start_distance = 0

        # Start first segment at earliest data found while adding the data
        self._add_segment_start(self.start)

        for key, data in self.data_dict.items():
            if "lat" in data:  # This is a location record
                if last_location:
                    if data["lat"] == 90 and data["lon"] == -80:
                        # Pause or stop records (lat = 90, long = -80, alt = 0) and handle segment data creation
                        # Use timestamp and distance of last (location) record
                        logging.getLogger(PROGRAM_NAME).debug("Start pause at %s in %s", data["t"], self.activity_id)
                        paused = True
                        self._add_segment_stop(last_location["t"], last_location["distance"] - segment_start_distance)
                    elif "lat" not in last_location:
                        # GPS was lost and is now back. Set distance to last known distance and use this record as the
                        # last known location.
                        if paused:
                            logging.getLogger(PROGRAM_NAME).debug("Stop pause at %s in %s", data["t"], self.activity_id)
                            paused = False
                        logging.getLogger(PROGRAM_NAME).debug(
                            "GPS signal available at %s in %s. Calculating distance using location data.",
                            data["t"],
                            self.activity_id,
                        )
                        data["distance"] = last_location["distance"]
                        # If no current segment, create one
                        if not self._current_segment:
                            self._add_segment_start(data["t"])
                            segment_start_distance = last_location["distance"]
                        last_location = data
                    else:
                        # Regular location record. If no current segment, create one
                        if not self._current_segment:
                            self._add_segment_start(data["t"])
                            segment_start_distance = last_location["distance"]
                        if paused:
                            logging.getLogger(PROGRAM_NAME).debug("Stop pause at %s in %s", data["t"], self.activity_id)
                            paused = False
                        # Calculate and set the accumulative distance of the location record
                        segment_distance = batched_distances[batched_distance_index]
                        batched_distance_index += 1
                        data["distance"] = segment_distance + last_location["distance"]
                        last_location = data
                else:
                    # First location. Set distance 0
                    data["distance"] = 0
                    segment_start_distance = 0
                    last_location = data
            # Do not process speed records for open water swim activities
            elif "rs" in data and self._activity_type != HiActivity.TYPE_OPEN_WATER_SWIM:
                if last_location:
                    time_delta = data["t"] - last_location["t"]
                    if not paused and ("lat" not in last_location or time_delta > GPS_TIMEOUT):
                        # GPS signal lost for more than the GPS timeout period. Calculate distance based on speed records
                        logging.getLogger(PROGRAM_NAME).debug(
                            "No GPS signal between %s and %s in %s. Calculating distance using speed data (%s dm/s)",
                            last_location["t"],
                            data["t"],
                            self.activity_id,
                            data["rs"],
                        )
                        # If no current segment, create one
                        if not self._current_segment:
                            self._add_segment_start(data["t"])
                            segment_start_distance = last_location["distance"]
                        data["distance"] = last_location["distance"] + (data["rs"] * time_delta.seconds / 10)
                        last_location = data
                else:
                    # No location records processed and speed record available = start without GPS or no GPS at all.
                    # Set distance 0
                    data["distance"] = 0
                    segment_start_distance = 0
                    last_location = data
            elif "alti" in data:
                # Retain first altitude as start altitude parameter.
                # Retained as a reusable start altitude marker for export pipelines.
                if "altitude start" not in self.activity_params:
                    self.activity_params["altitude start"] = data["alti"]

        # Close last segment if it is still open
        if self._current_segment:
            # If the segment is open (no stop record for end of activity):
            # - Outdoor activities -> calculated distance data is available, use timestamp and distance of last location record.
            # - Indoor activities -> no calculated distance data available, use stop timestamp and total distance from the header information.
            if last_location:
                # Outdoor
                self._add_segment_stop(last_location["t"], last_location["distance"] - segment_start_distance)
            else:
                # Indoor
                self._add_segment_stop(self.stop, self.distance)

        # Set the total distance of the activity
        if last_location:
            # Outdoor
            self.calculated_distance = int(last_location["distance"])
        else:
            # Indoor
            self.calculated_distance = self.distance

        if self.distance < 0:
            if self.calculated_distance < 0:
                self.calculated_distance = 0
            self.distance = self.calculated_distance

    def get_segment_data(self, segment: dict) -> list:
        """ " Returns a filtered and sorted data set containing all raw parsed data from the requested segment"""
        # Filter data
        if segment["stop"]:
            segment_data_dict = {k: v for k, v in self.data_dict.items() if segment["start"] <= k <= segment["stop"]}
        else:
            # E.g. for swimming activities, the last segment is not closed due to no stop record nor valid record that
            # indicates the end of the activity. Return all remaining data starting from the start timestamp
            segment_data_dict = {k: v for k, v in self.data_dict.items() if segment["start"] <= k}

        # Sort data by timestamp (sort on key in data dictionary)
        segment_data = [value for (key, value) in sorted(segment_data_dict.items())]
        return segment_data

    def normalize_distances(self):
        # Make sure segment and distance data is calculated.
        segments = self.get_segments()

        if self.calculated_distance == 0 or self.distance == 0 or self.calculated_distance == self.distance:
            return

        logging.getLogger(PROGRAM_NAME).debug("Normalizing distance data for activity %s", self.activity_id)

        normalize_ratio = self.calculated_distance / self.distance
        for n, segment in enumerate(segments):
            segment["distance"] = segment["distance"] / normalize_ratio
            segment_data = self.get_segment_data(segment)
            if segment_data:
                for data in segment_data:
                    if "distance" in data:
                        data["distance"] = data["distance"] / normalize_ratio

    def get_swim_data(self) -> Optional[list]:
        if self.get_activity_type() == self.TYPE_POOL_SWIM:
            if self.swim_data:
                return self.swim_data
            else:
                return self._calc_pool_swim_data()
        elif self.get_activity_type() == self.TYPE_OPEN_WATER_SWIM:
            return self._get_open_water_swim_data()
        else:
            return None

    def _calc_pool_swim_data(self) -> list:
        """Calculates the real swim (lap) data based on the raw parsed pool swim data
        The following calculation steps on the raw parsed data is applied.
        1. Starting point is the raw parsed data per lap (segment). The data consists of multiple data records
           with a 5-second time interval containing the same SWOLF and stroke frequency (in strokes/minute) values.
        2. Calculate the number of strokes in the lap.
           Number of strokes = stroke frequency x (last - first lqp timestamp) / 60
            3. Calculate the lap time: lap time = SWOLF - number of strokes

        :return:
        A list of lap data dictionaries containing the following data:
           'lap' : lap number in the activity
           'start' : Start timestamp of the lap
           'stop' : Stop timestamp of the lap
           'duration' : lap duration in seconds
           'swolf' : lap SWOLF value (duration + number of strokes in lap)
           'strokes' : number of strokes in lap
           'speed' : estimated average speed during the lap in m/s.
                     Note: this is an approximate value as the minimum resolution of the raw speed data is 1 dm/s
           'distance' : estimated distance based on the average speed and the lap duration.
                        Note: this is an approximate value as the minimum resolution of the raw speed data is 1 dm/s
        """
        logging.getLogger(PROGRAM_NAME).info("Calculating swim data for activity %s", self.activity_id)

        swim_data = []

        # Sort the data dictionary by timestamp
        self.data_dict = collections.OrderedDict(sorted(self.data_dict.items()))

        total_distance = 0

        for n, segment in enumerate(self._segment_list):
            segment_data = self.get_segment_data(segment)
            first_swf_index = 0
            while "swf" not in segment_data[first_swf_index]:
                first_swf_index += 1
            first_lap_record = segment_data[first_swf_index]
            last_lap_record = segment_data[-1]

            # First record is after 5 s in lap
            raw_data_duration = (last_lap_record["t"] - first_lap_record["t"]).total_seconds() + 5

            lap_data = {}
            lap_data["lap"] = n + 1
            lap_data["swolf"] = first_lap_record["swf"]
            lap_data["strokes"] = round(
                first_lap_record["p-f"] * raw_data_duration / 60
            )  # Convert strokes/min -> strokes/lap
            lap_data["duration"] = lap_data["swolf"] - lap_data["strokes"]  # Derive lap time from SWOLF - strokes
            if self.pool_length < 1:
                # Pool length not set. Derive estimated distance from raw speed data
                lap_data["speed"] = first_lap_record["rs"] / 10  # estimation in m/s
                lap_data["distance"] = lap_data["speed"] * lap_data["duration"]
            else:
                lap_data["distance"] = self.pool_length
                lap_data["speed"] = self.pool_length / lap_data["duration"]

            total_distance += lap_data["distance"]

            # Start timestamp of lap
            if not swim_data:
                lap_data["start"] = self.start
            else:
                # Start of this lap is stop of previous lap
                lap_data["start"] = swim_data[-1]["stop"]
            # Stop timestamp of lap
            lap_data["stop"] = lap_data["start"] + dts_delta(seconds=lap_data["duration"])

            logging.getLogger(PROGRAM_NAME).debug("Calculated swim data for lap %d : %s", n + 1, lap_data)

            swim_data.append(lap_data)

        # Update activity distance
        self.calculated_distance = total_distance
        if self.distance < 0:
            self.distance = self.calculated_distance

        return swim_data

    def _get_open_water_swim_data(self) -> list:
        """Calculates the real swim (lap) data based on the raw parsed open water swim data"""
        logging.getLogger(PROGRAM_NAME).info("Calculating swim data for activity %s", self.activity_id)

        swim_data = []

        # Sort the data dictionary by timestamp
        self.data_dict = collections.OrderedDict(sorted(self.data_dict.items()))

        # The generated segment list based on the SWOLF data is unusable for open water swim activities.
        # Reset it and recalculate segments and distances based on the GPS location data.
        self._reset_segments()
        self._calc_segments_and_distances()

        # Create 1 large lap
        lap_data = {
            "lap": 1,
            "start": self.start,
            "stop": self.stop,
            "duration": (self.stop - self.start).seconds,
            "distance": self.distance,
        }
        swim_data.append(lap_data)

        return swim_data

    def __repr__(self):
        # TODO verify timezone (un)aware display date / time
        to_string = (
            self.__class__.__name__
            + "\nID       : "
            + self.activity_id
            + "\nType     : "
            + self._activity_type
            + "\nDate     : "
            + self.start.date().isoformat()
            + " (YYYY-MM-DD)"
            + "\nDuration : "
            + str(self.stop - self.start)
            + " (H:MM:SS)"
            "\nDistance : " + str(self.calculated_distance) + "m (Huawei: " + str(self.distance) + " m)"
        )
        return to_string
