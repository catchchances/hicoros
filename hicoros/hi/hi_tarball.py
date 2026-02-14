import datetime
import logging
import os
import tarfile

from hicoros.constants import OUTPUT_DIR
from hicoros.constants import PROGRAM_NAME
from hicoros.hi.hi_track_file import HiTrackFileParser
from hicoros.time_utils import convert_hitrack_timestamp


class HiTarBallParser:
    _TAR_HITRACK_DIR = "com.huawei.health/files"
    _HITRACK_FILE_START = "HiTrack_"

    def __init__(self, tarball_filename: str, extract_dir: str = OUTPUT_DIR):
        if not tarball_filename:
            logging.getLogger(PROGRAM_NAME).error("Parameter HiHealth tarball filename is missing")

        try:
            self.tarball = tarfile.open(tarball_filename, "r")
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error("Error opening tarball file <%s>\n%s", tarball_filename, e)
            raise Exception("Error opening tarball file <%s>", tarball_filename)

        self.extract_dir = extract_dir
        self.hi_activity_list = []

    def parse(self, from_date: datetime.date = datetime.date(1970, 1, 1)) -> list:
        try:
            for tar_info in self.tarball.getmembers():
                if tar_info.path.startswith(self._TAR_HITRACK_DIR) and os.path.basename(tar_info.path).startswith(
                    self._HITRACK_FILE_START
                ):
                    hitrack_filename = os.path.basename(tar_info.path)
                    logging.getLogger(PROGRAM_NAME).info(
                        "Found HiTrack file <%s> in tarball <%s>", hitrack_filename, self.tarball.name
                    )
                    if from_date:
                        hitrack_file_date = convert_hitrack_timestamp(
                            float(hitrack_filename[len(self._HITRACK_FILE_START) : len(self._HITRACK_FILE_START) + 10])
                        ).date()
                        if hitrack_file_date >= from_date:
                            self._extract_and_parse_hitrack_file(tar_info)
                        else:
                            logging.getLogger(PROGRAM_NAME).info(
                                "Skipped parsing HiTrack file <%s> being an activity from %s before %s (YYYYMMDD).",
                                hitrack_filename,
                                hitrack_file_date.isoformat(),
                                from_date.isoformat(),
                            )
                    else:
                        self._extract_and_parse_hitrack_file(tar_info)
            return self.hi_activity_list
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error("Error parsing tarball <%s>\n%s", self.tarball.name, e)
            raise Exception("Error parsing tarball <%s>", self.tarball.name)

    def _extract_and_parse_hitrack_file(self, tar_info):
        try:
            tar_info.name = os.path.basename(tar_info.name)
            self.tarball.extract(tar_info, self.extract_dir)
            hitrack_file = HiTrackFileParser(self.extract_dir + "/" + tar_info.path)
            hi_activity = hitrack_file.parse()
            self.hi_activity_list.append(hi_activity)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                "Error parsing HiTrack file <%s> in tarball <%s>", tar_info.path, self.tarball.name, e
            )

    def _close_tarball(self):
        try:
            if self.tarball:
                self.tarball.close()
                logging.getLogger(PROGRAM_NAME).debug("Tarball <%s> closed", self.tarball.name)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error("Error closing tarball <%s>\n", self.tarball.name, e)

    def __del__(self):
        self._close_tarball()
