import argparse
import logging
import re
import sys
from datetime import datetime as dts


def create_argument_parser(activity_types, output_dir: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    json_group = parser.add_argument_group("JSON options")
    json_group.add_argument(
        "-z",
        "--zip",
        help="The filename of the Huawei Cloud ZIP file containing \
                                                 the JSON file(s) with the motion path detail data to convert. \
                                                 The JSON file(s) will be extracted to the directory in the --output_dir \
                                                 argument and conversion will be performed.",
    )

    json_group.add_argument(
        "-p",
        "--password",
        help="The password of the encrypted Huawei Cloud ZIP file. \
                                                     Required for encrypted ZIP files only.",
    )

    json_group.add_argument(
        "-j",
        "--json",
        help="The filename of a Huawei Cloud JSON file containing the motion path \
                                                  detail data to convert or the filename of the Huawei Cloud ZIP file \
                                                  containing the JSON file with the motion path detail data (this will \
                                                  work identical to --zip argument above).",
    )

    json_group.add_argument(
        "--json_export",
        help="Exports a file with the JSON data of each single activity that is \
                                                   converted from the JSON file in the --json argument. The file will \
                                                   be exported to the directory in the --output_dir argument with a \
                                                   .json file extension. The exported file can be reused in the \
                                                   --json argument to e.g. run the conversion again for the JSON \
                                                   activity or for debugging purposes.",
        action="store_true",
    )

    json_group.add_argument(
        "--json_sport_filter",
        help="Applicable to --json and --zip options only. Convert only JSON activities with the "
        "specified internal sport type(s). Example: --json_sport_filter Run Indoor_Run",
        nargs="+",
        choices=[
            activity_types.TYPE_WALK,
            activity_types.TYPE_RUN,
            activity_types.TYPE_CYCLE,
            activity_types.TYPE_POOL_SWIM,
            activity_types.TYPE_OPEN_WATER_SWIM,
            activity_types.TYPE_HIKE,
            activity_types.TYPE_MOUNTAIN_HIKE,
            activity_types.TYPE_INDOOR_RUN,
            activity_types.TYPE_INDOOR_CYCLE,
            activity_types.TYPE_CROSS_TRAINER,
            activity_types.TYPE_OTHER,
            activity_types.TYPE_CROSS_COUNTRY_RUN,
        ],
    )
    file_group = parser.add_argument_group("FILE options")
    file_group.add_argument("-f", "--file", help="The filename of a single HiTrack file to convert.")
    file_group.add_argument(
        "-s",
        "--sport",
        help="Force sport for the conversion. Sport will be auto-detected when \
                                                   this option is not used.",
        type=str,
        choices=[
            activity_types.TYPE_WALK,
            activity_types.TYPE_RUN,
            activity_types.TYPE_CYCLE,
            activity_types.TYPE_POOL_SWIM,
            activity_types.TYPE_OPEN_WATER_SWIM,
        ],
    )

    tar_group = parser.add_argument_group("TAR options")
    tar_group.add_argument(
        "-t",
        "--tar",
        help="The filename of an (unencrypted) tarball with HiTrack files to \
                                                convert.",
    )

    date_group = parser.add_argument_group("DATE options")

    def from_date_type(arg):
        try:
            return dts.strptime(arg, "%Y-%m-%d").date()
        except ValueError:
            msg = "Invalid date or date format (expected YYYY-MM-DD): '{0}'.".format(arg)
            raise argparse.ArgumentTypeError(msg)

    date_group.add_argument(
        "--from_date",
        help="Applicable to --json and --tar options only. Only convert HiTrack \
                                                 information from the JSON file or from HiTrack files in the tarball \
                                                 if the activity started on FROM_DATE or later. Format YYYY-MM-DD",
        type=from_date_type,
        default="1970-01-01",
    )

    swim_group = parser.add_argument_group("SWIM options")

    def pool_length_type(arg):
        l = int(arg)
        if l < 1:
            raise argparse.ArgumentTypeError("Pool length must be an positive integer value.")
        if l == 1013:
            print("Congrats on your swim in the Alfonso del Mar.")
        return l

    swim_group.add_argument(
        "--pool_length",
        help="The pool length in meters to use for swimming activities. \
                                                  If the option is not set, the estimated pool length derived from \
                                                  the available speed data in the HiTrack file will be used. Note \
                                                  that the available speed data has a minimum resolution of 1 dm/s.",
        type=pool_length_type,
    )

    output_group = parser.add_argument_group("OUTPUT options")
    output_group.add_argument(
        "--output_dir",
        help="The path to the directory to store the output files. The default \
                                             directory is "
        + output_dir
        + ".",
        default=output_dir,
    )
    output_group.add_argument(
        "--use_original_filename",
        help="In single FILE or TAR mode, when using this option the converted FIT files will \
                              have the same filename as the original input file (except from the file extension).",
        action="store_true",
    )
    output_group.add_argument(
        "--output_file_prefix",
        help="Adds the strftime representation of this argument as a prefix to the generated \
                              FIT file(s). E.g. use %%Y-%%m-%%d- to add human readable year-month-day information \
                              in the name of the generated FIT file.",
        type=str,
    )
    parser.add_argument(
        "--log_level", help="Set the logging level.", type=str, choices=["INFO", "DEBUG"], default="INFO"
    )

    return parser


def sanitize_args_string(args_string: str) -> str:
    return re.sub(r"'(--password|-p)',\s*'[^']*'", "'--password', '********'", args_string)


def init_runtime(
    parser: argparse.ArgumentParser, init_logging, program_name: str, version: tuple[str, str, str, str, str]
):
    args = parser.parse_args()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        input("\nPress enter to exit.")
        sys.exit(2)

    if args.log_level:
        init_logging(args.log_level)
    else:
        init_logging()

    args_string = sanitize_args_string(str(sys.argv[1:]))
    logging.getLogger(program_name).info(
        "%s version %s.%s.%s (build %s.%s) started with arguments %s",
        program_name,
        version[0],
        version[1],
        version[2],
        version[3],
        version[4],
        args_string,
    )
    logging.getLogger(program_name).info(
        "Running on Python version %s.%s.%s", sys.version_info[0], sys.version_info[1], sys.version_info[2]
    )

    return args
