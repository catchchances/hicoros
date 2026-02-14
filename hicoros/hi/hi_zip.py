import logging
import platform
import subprocess
import zipfile
from typing import Optional
from zipfile import ZipFile

from hicoros.constants import OUTPUT_DIR
from hicoros.constants import PROGRAM_NAME


class HiZipReader:
    @staticmethod
    def extract_json_list(zip_filename: str, output_dir: str = OUTPUT_DIR, password: str = None) -> Optional[list]:
        _MOTION_PATH_JSON_DIR = "Motion path detail data & description"

        if not zipfile.is_zipfile(zip_filename):
            message = f"Invalid ZIP file or ZIP file not found <{zip_filename}>"
            logging.getLogger(PROGRAM_NAME).error(message)
            raise Exception(message)

        if not password:
            message = f"ZIP file <{zip_filename}> is encrypted but no password is provided"
            logging.getLogger(PROGRAM_NAME).error(message)
            raise Exception(message)

        zip_json_filenames = f"{_MOTION_PATH_JSON_DIR}/*.json"

        huawei_zip = zipfile.ZipFile(zip_filename)
        huawei_json_filenames = [
            f"{output_dir}/{f.filename.split('/')[-1]}"
            for f in huawei_zip.infolist()
            if f.filename.startswith(_MOTION_PATH_JSON_DIR + "/") and f.filename.endswith(".json")
        ]

        if platform.system() in ["Windows", "Linux", "Darwin"]:
            unzip_cmd = (
                "7za",
                "e",
                "-aoa",
                "-o%s" % output_dir,
                "-bb0",
                "-bse0",
                "-bsp2",
                "-p%s" % password,
                "-sccUTF-8",
                "%s" % zip_filename,
                "--",
                "%s" % zip_json_filenames,
            )
        else:
            message = (f"Encrypted ZIP files in Huawei 2025 format not supported on platform {platform.system()}",)
            logging.getLogger(PROGRAM_NAME).error(message)
            raise NotImplementedError(message)
        completed_process = subprocess.run(
            unzip_cmd, universal_newlines=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE
        )
        logging.getLogger(PROGRAM_NAME).info(completed_process.stdout)
        if completed_process.returncode != 0:
            message = f"Error extracting JSON files from encrypted ZIP file <{zip_filename}>. Return code was {completed_process.returncode}"
            logging.getLogger(PROGRAM_NAME).error(message)
            raise Exception(message)

        return huawei_json_filenames

    @staticmethod
    def extract_json(zip_filename: str, output_dir: str = OUTPUT_DIR, password: str = None):
        _MOTION_PATH_JSON_FILENAME = "data/Motion path detail data & description/motion path detail data.json"
        _MOTION_PATH_JSON_FILENAME_ALT = "Motion path detail data & description/motion path detail data.json"
        _WINDOWS_UNZIP_CMD = '7za x -aoa "-o%s" -bb0 -bse0 -bsp2 "-p%s" -sccUTF-8 "%s" -- "%s"'
        _MACOS_UNZIP_CMD = "unzip %s -P %s -d %s %s "

        if not zipfile.is_zipfile(zip_filename):
            logging.getLogger(PROGRAM_NAME).error("Invalid ZIP file or ZIP file not found <%s>", zip_filename)
            raise Exception("Invalid ZIP file or ZIP file not found <%s>", zip_filename)

        if password is not None:
            zip_json_filename = _MOTION_PATH_JSON_FILENAME_ALT
            if platform.system() == "Windows":
                unzip_cmd = _WINDOWS_UNZIP_CMD % (output_dir, password, zip_filename, zip_json_filename)
            elif platform.system() == "Darwin":
                unzip_cmd = _MACOS_UNZIP_CMD % (zip_filename, password, output_dir, zip_json_filename)
            else:
                logging.getLogger(PROGRAM_NAME).error(
                    "Encrypted ZIP files not supported on platform %s", platform.system()
                )
                raise NotImplementedError("Encrypted ZIP files not supported on platform %s", platform.system())
            completed_process = subprocess.run(
                unzip_cmd, universal_newlines=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE
            )
            logging.getLogger(PROGRAM_NAME).info(completed_process.stdout)
            if completed_process.returncode != 0:
                logging.getLogger(PROGRAM_NAME).error(
                    "Error extracting JSON file <%s> from encrypted ZIP file <%s>. Return code was %s",
                    zip_json_filename,
                    zip_filename,
                    completed_process.returncode,
                )
                raise Exception(
                    "Error extracting JSON file <%s> from encrypted ZIP file <%s>. Return code was %s",
                    zip_json_filename,
                    zip_filename,
                    completed_process.returncode,
                )
        else:
            with ZipFile(zip_filename, "r", True) as hi_zip:
                if _MOTION_PATH_JSON_FILENAME in hi_zip.namelist():
                    zip_json_filename = _MOTION_PATH_JSON_FILENAME
                elif _MOTION_PATH_JSON_FILENAME_ALT in hi_zip.namelist():
                    zip_json_filename = _MOTION_PATH_JSON_FILENAME_ALT
                else:
                    logging.getLogger(PROGRAM_NAME).warning(
                        "Could not find JSON file <%s> in ZIP file <%s>. \
                                                            Nothing to convert.",
                        _MOTION_PATH_JSON_FILENAME,
                        zip_filename,
                    )
                    raise Exception(
                        "Could not find file <data/motion path detail data.json> in ZIP file <%s>. \
                                    Nothing to convert.",
                        zip_filename,
                    )

                try:
                    hi_zip.extract(zip_json_filename, output_dir)
                except Exception as e:
                    logging.getLogger(PROGRAM_NAME).error(
                        "Error extracting JSON file <%s> from ZIP file <%s>\n%s", zip_json_filename, zip_filename, e
                    )
                    raise Exception(
                        "Error extracting JSON file <%s> from ZIP file <%s>", zip_json_filename, zip_filename
                    )

        json_filename = output_dir + "/" + zip_json_filename
        return json_filename
