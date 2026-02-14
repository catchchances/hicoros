import csv
import datetime
import logging
from pathlib import Path

from hicoros.constants import PROGRAM_NAME
from hicoros.hi.hi_activity import HiActivity
from hicoros.time_utils import convert_hitrack_timestamp


class HiTrackFileParser:
    """The HiTrackFileParser class represents a single HiTrack file. It contains all file handling and parsing methods."""

    def __init__(
        self,
        hitrack_filename: str,
        activity_type: str = HiActivity.TYPE_UNKNOWN,
        timestamp_ref: datetime = None,
        start_timestamp_ref: datetime = None,
    ):
        if not hitrack_filename:
            logging.getLogger(PROGRAM_NAME).error(f"Parameter HiTrack filename is missing")

        self.hitrack_file = None
        self.hitrack_file = open(hitrack_filename, "r")

        self.activity = None
        self.activity_type = activity_type

        self.start = self._parse_timestamp_from_filename(8, 18)
        self.stop = self._parse_timestamp_from_filename(20, 30)

        self.timestamp_ref = timestamp_ref
        self.start_timestamp_ref = start_timestamp_ref

    def parse(self) -> HiActivity:
        if self.activity:
            return self.activity

        logging.getLogger(PROGRAM_NAME).info(f"Parsing file <{self.hitrack_file.name}>")

        self.activity = HiActivity(
            Path(self.hitrack_file.name).name, self.activity_type, self.timestamp_ref, self.start_timestamp_ref
        )

        data_list = []
        with self.hitrack_file:
            csv_reader = csv.reader(self.hitrack_file, delimiter=";")
            for line in csv_reader:
                data_list.clear()
                if line[0] == "tp=lbs":
                    for item in line[1:]:
                        key_value = item.split("=", 1)
                        if len(key_value) == 2 and key_value[0] in {"k", "lat", "lon", "t"}:
                            data_list.append(key_value)
                    self.activity.add_location_data(data_list)
                elif line[0] == "tp=h-r":
                    for data_index in [1, 2]:
                        data_list.append(line[data_index].split("="))
                    self.activity.add_heart_rate_data(data_list)
                elif line[0] == "tp=alti":
                    for data_index in [1, 2]:
                        data_list.append(line[data_index].split("="))
                    self.activity.add_altitude_data(data_list)
                elif line[0] == "tp=s-r":
                    for item in line[1:]:
                        key_value = item.split("=", 1)
                        if len(key_value) == 2 and key_value[0] in {"k", "v"}:
                            data_list.append(key_value)
                    self.activity.add_step_frequency_data(data_list)
                elif line[0] == "tp=swf":
                    for data_index in [1, 2]:
                        data_list.append(line[data_index].split("="))
                    self.activity.add_swolf_data(data_list)
                elif line[0] == "tp=p-f":
                    for data_index in [1, 2]:
                        data_list.append(line[data_index].split("="))
                    self.activity.add_stroke_frequency_data(data_list)
                elif line[0] == "tp=rs" or line[0] == "Tp=rs":
                    for item in line[1:]:
                        key_value = item.split("=", 1)
                        if len(key_value) == 2 and key_value[0] in {"k", "v"}:
                            data_list.append(key_value)
                    self.activity.add_speed_data(data_list)
                elif line[0] == "tp=pm-n":
                    for data_index in [1, 2]:
                        data_list.append(line[data_index].split("="))
                    self.activity.add_interval_pace_data(data_list)
                elif line[0] == "tp=p-m":
                    for data_index in [1, 2]:
                        data_list.append(line[data_index].split("="))
                    self.activity.add_pace_data(data_list)
                elif line[0] == "tp=r-pm":
                    for item in line[1:]:
                        key_value = item.split("=", 1)
                        if len(key_value) == 2 and key_value[0] in {"k", "s", "P", "p"}:
                            data_list.append(key_value)
                    self.activity.add_realtime_speed_pace_data(data_list)

        return self.activity

    def _parse_timestamp_from_filename(self, start_index: int, end_index: int):
        timestamp_part = Path(self.hitrack_file.name).name[start_index:end_index]
        if len(timestamp_part) == 10 and timestamp_part.isdigit():
            return convert_hitrack_timestamp(float(timestamp_part))
        return None

    def _close_file(self):
        if self.hitrack_file and not self.hitrack_file.closed:
            self.hitrack_file.close()
            logging.getLogger(PROGRAM_NAME).debug(f"HiTrack file <{self.hitrack_file.name}> closed")

    def __del__(self):
        self._close_file()
