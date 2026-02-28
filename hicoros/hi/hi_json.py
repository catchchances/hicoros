import datetime
import json
import logging
import re
from datetime import datetime as dts
from datetime import timedelta as dts_delta
from datetime import timezone as tz
from pathlib import Path
from typing import Optional

from hicoros.constants import OUTPUT_DIR
from hicoros.constants import PROGRAM_NAME
from hicoros.hi.hi_activity import HiActivity
from hicoros.hi.hi_track_file import HiTrackFileParser
from hicoros.time_utils import get_tz_aware_datetime


class HiJsonParser:
    _JSON_SPORT_TYPES = [
        (5, HiActivity.TYPE_WALK),
        (4, HiActivity.TYPE_RUN),
        (3, HiActivity.TYPE_CYCLE),
        (102, HiActivity.TYPE_POOL_SWIM),
        (104, HiActivity.TYPE_OPEN_WATER_SWIM),
        (282, HiActivity.TYPE_HIKE),
        (2, HiActivity.TYPE_MOUNTAIN_HIKE),
        (101, HiActivity.TYPE_INDOOR_RUN),
        (103, HiActivity.TYPE_INDOOR_CYCLE),
        (111, HiActivity.TYPE_CROSS_TRAINER),
        (117, HiActivity.TYPE_OTHER),
        (145, HiActivity.TYPE_CROSSFIT),
        (118, HiActivity.TYPE_CROSS_COUNTRY_RUN),
    ]

    _UNSUPPORTED_JSON_SPORT_TYPES = []

    _SPORT_DATA_SOURCE_MANUAL = 2

    def __init__(
        self,
        json_filename: str,
        output_dir: str = OUTPUT_DIR,
        export_json_data: bool = False,
        include_activity_types: Optional[set[str]] = None,
    ):
        if not json_filename:
            logging.getLogger(PROGRAM_NAME).error(f"Parameter for JSON filename is missing")

        self.json_file = None
        self.json_file = open(json_filename, "r")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.export_json_data = export_json_data
        self.include_activity_types = include_activity_types

        self.hi_activity_list = []

    def parse(self, from_date: datetime.date = datetime.date(1970, 1, 1)) -> list:
        activity_index = -1
        activity_snippet = "<unavailable>"
        try:
            json_string = self.json_file.read()
            json_string = re.sub('"partTimeMap":{(.*?)},', "", json_string)
            data = json.loads(json_string)

            for activity_index, activity_dict in enumerate(data):
                activity_snippet = repr(activity_dict)
                if len(activity_snippet) > 300:
                    activity_snippet = activity_snippet[:300] + "...(truncated)"

                if "recordDay" in activity_dict:
                    activity_date = dts.strptime(str(activity_dict["recordDay"]), "%Y%m%d").date()
                else:
                    activity_date = dts.fromtimestamp(activity_dict["startTime"] / 1000, datetime.UTC).date()

                if activity_date >= from_date:
                    logging.getLogger(PROGRAM_NAME).info(
                        f"Found one or more activities in JSON at index {activity_index} "
                        f"to parse from {activity_date.isoformat()} (YYY-MM-DD)"
                    )

                    if "motionPathData" in activity_dict:
                        for motion_path_dict in activity_dict["motionPathData"]:
                            hi_activity = self._parse_activity(motion_path_dict)
                            if hi_activity:
                                self.hi_activity_list.append(hi_activity)
                    else:
                        hi_activity = self._parse_activity(activity_dict)
                        if hi_activity:
                            self.hi_activity_list.append(hi_activity)

                else:
                    logging.getLogger(PROGRAM_NAME).info(
                        f"Skipped parsing activity at index {activity_index} being an activity from "
                        f"{activity_date.isoformat()} before {from_date.isoformat()} (YYYY-MM-DD)."
                    )

            if activity_index == -1:
                logging.getLogger(PROGRAM_NAME).info(
                    f"No activities found to convert in JSON file <{self.json_file.name}>"
                )
            return self.hi_activity_list
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                f"Error parsing JSON file <{self.json_file.name}> at activity index <{activity_index}>\n"
                f"Raw snippet: {activity_snippet}\n{type(e).__name__}: {e}"
            )
            raise Exception(
                f"Error parsing JSON file <{self.json_file.name}> at activity index <{activity_index}>\n"
                f"Raw snippet: {activity_snippet}\n{type(e).__name__}: {e}"
            ) from e

    def _parse_activity(self, activity_dict: dict) -> Optional[HiActivity]:
        sport_type = activity_dict["sportType"]
        if sport_type in self._UNSUPPORTED_JSON_SPORT_TYPES:
            activity_start = dts.fromtimestamp(activity_dict["startTime"] / 1000, datetime.UTC)
            logging.getLogger(PROGRAM_NAME).warning(
                f"Activity from {activity_start} has an unsupported activity type {sport_type} "
                f"and will NOT be converted."
            )
            return

        sport = HiActivity.TYPE_UNKNOWN
        if any(activity_dict["sportType"] in i for i in self._JSON_SPORT_TYPES):
            sport = [item[1] for item in self._JSON_SPORT_TYPES if item[0] == sport_type][0]

        if self.include_activity_types and sport not in self.include_activity_types:
            activity_start = dts.fromtimestamp(activity_dict["startTime"] / 1000, datetime.UTC)
            logging.getLogger(PROGRAM_NAME).info(
                f"Skipped activity from {activity_start} due to sport filter ({sport})."
            )
            return

        hitrack_data = activity_dict["attribute"]
        hitrack_data = re.sub("HW_EXT_TRACK_DETAIL@is", "", hitrack_data)
        hitrack_data = re.sub("&&HW_EXT_TRACK_SIMPLIFY@is(.*)", "", hitrack_data, flags=re.DOTALL)

        activity_detail_data = activity_dict["attribute"]
        activity_detail_data = re.sub(
            "HW_EXT_TRACK_DETAIL@is(.*)&&HW_EXT_TRACK_SIMPLIFY@is", "", activity_detail_data, flags=re.DOTALL
        )
        activity_detail_dict = json.loads(activity_detail_data)

        time_zone_string = activity_dict["timeZone"]
        time_zone_hours_offset = int(time_zone_string[:3])
        time_zone_minutes_offset = int(time_zone_string[3:])
        time_zone = tz(dts_delta(hours=time_zone_hours_offset, minutes=time_zone_minutes_offset))

        activity_start = dts.fromtimestamp(activity_dict["startTime"] / 1000, datetime.UTC)

        hitrack_path = (
            self.output_dir
            / f"HiTrack_{get_tz_aware_datetime(activity_start, time_zone).strftime('%Y%m%d_%H%M%S')}"
        )

        if self.export_json_data:
            json_filename = hitrack_path.with_suffix(".json")
            logging.getLogger(PROGRAM_NAME).info(
                f"Exporting JSON data of activity from {activity_start} to file {json_filename}"
            )
            with open(json_filename, "w+") as json_file:
                json_file.write("[")
                json.dump(activity_dict, json_file)
                json_file.write("]")

        logging.getLogger(PROGRAM_NAME).info(
            f"Saving activity from {activity_start} to HiTrack file {hitrack_path} for parsing"
        )
        with open(hitrack_path, "w+") as hitrack_file:
            hitrack_file.write(hitrack_data)

        if sport == HiActivity.TYPE_POOL_SWIM:
            activity_id = hitrack_path.name
            hi_activity = None
            if "mSwimSegments" in activity_detail_dict:
                hi_activity = HiActivity.from_json_pool_swim_data(
                    activity_id, activity_start, activity_detail_dict["mSwimSegments"]
                )
            else:
                sport_data_source = activity_dict["sportDataSource"]
                if sport_data_source == self._SPORT_DATA_SOURCE_MANUAL:
                    logging.getLogger(PROGRAM_NAME).info(
                        f"Swimming activity {activity_id} has been manually added, conversion will only contain basic "
                        f"activity data."
                    )
                    hi_activity = HiActivity.from_manual_json_pool_swim_data(
                        activity_id, activity_start, activity_dict["totalTime"], activity_dict["totalDistance"]
                    )
                else:
                    logging.getLogger(PROGRAM_NAME).warning(
                        f"Swimming activity {activity_id} with sport data source {sport_data_source} "
                        f"has no swim segment data and can not be converted."
                    )
                    return

            if hi_activity is None:
                logging.getLogger(PROGRAM_NAME).warning(
                    f"Swimming activity {activity_id} has empty swim segment data and can not be converted."
                )
                return
        else:
            timestamp_ref = datetime.datetime(
                year=activity_start.year, month=activity_start.month, day=activity_start.day
            )

            hitrack_file = HiTrackFileParser(
                str(hitrack_path), timestamp_ref=timestamp_ref, start_timestamp_ref=activity_start
            )
            hi_activity = hitrack_file.parse()
            if sport != HiActivity.TYPE_UNKNOWN:
                hi_activity.set_activity_type(sport)
            else:
                logging.getLogger(PROGRAM_NAME).warning(
                    f"Activity {hitrack_path.name} from {activity_start} has an unknown "
                    f"activity type {sport_type}. Conversion will be attempted but may not work."
                )

            if hi_activity.get_activity_type() == HiActivity.TYPE_OPEN_WATER_SWIM:
                hi_activity.get_swim_data()

        hi_activity.start = activity_start
        hi_activity.time_zone = time_zone
        hi_activity.stop = activity_start + dts_delta(milliseconds=activity_dict["totalTime"])
        hi_activity.timer_duration = activity_dict["totalTime"] / 1000.0

        if "totalDistance" in activity_detail_dict:
            hi_activity.distance = activity_detail_dict["totalDistance"]

        if "totalCalories" in activity_detail_dict:
            hi_activity.calories = activity_detail_dict["totalCalories"] / 1000

        if "wearSportData" in activity_detail_dict:
            if "swim_pool_length" in activity_detail_dict["wearSportData"]:
                hi_activity.set_pool_length(activity_detail_dict["wearSportData"]["swim_pool_length"] / 100)

        return hi_activity

    def _close_json(self):
        if self.json_file and not self.json_file.closed:
            self.json_file.close()
            logging.getLogger(PROGRAM_NAME).debug(f"JSON file <{self.json_file.name}> closed")

    def __del__(self):
        self._close_json()
