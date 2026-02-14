import logging
import zipfile

from hicoros.constants import PROGRAM_NAME
from hicoros.fit.fit_writer import build_fit_filename
from hicoros.fit.fit_writer import save_fit_file
from hicoros.hi.hi_track_file import HiTrackFileParser
from hicoros.hi.hi_json import HiJsonParser
from hicoros.hi.hi_tarball import HiTarBallParser
from hicoros.hi.hi_zip import HiZipReader


def convert_single_file_mode(args):
    if args.sport:
        hi_file = HiTrackFileParser(args.file, args.sport)
    else:
        hi_file = HiTrackFileParser(args.file)
    hi_activity = hi_file.parse()
    if args.pool_length:
        hi_activity.set_pool_length(args.pool_length)

    fit_filename = None
    if not args.use_original_filename:
        fit_filename = build_fit_filename(args.output_dir, hi_activity)

    save_fit_file(
        hi_activity,
        save_dir=args.output_dir,
        filename_prefix=args.output_file_prefix,
        fit_filename=fit_filename,
    )

    logging.getLogger(PROGRAM_NAME).info("Converted %s", hi_activity)


def convert_tar_mode(args):
    hi_tarball = HiTarBallParser(args.tar)
    hi_activity_list = hi_tarball.parse(args.from_date)
    for hi_activity in hi_activity_list:
        if args.pool_length:
            hi_activity.set_pool_length(args.pool_length)

        fit_filename = None
        if not args.use_original_filename:
            fit_filename = build_fit_filename(args.output_dir, hi_activity)

        save_fit_file(
            hi_activity,
            save_dir=args.output_dir,
            filename_prefix=args.output_file_prefix,
            fit_filename=fit_filename,
        )

        logging.getLogger(PROGRAM_NAME).info("Converted %s", hi_activity)


def resolve_json_filename_list(args):
    json_filename_list = None
    json_filename = None

    if args.zip:
        json_filename_list = HiZipReader.extract_json_list(args.zip, args.output_dir, args.password)
        if not json_filename_list:
            json_filename = HiZipReader.extract_json(args.zip, args.output_dir, args.password)
    elif args.json and zipfile.is_zipfile(args.json):
        json_filename = HiZipReader.extract_json(args.json, args.output_dir, args.password)
    else:
        json_filename = args.json

    if not json_filename_list and json_filename:
        json_filename_list = [json_filename]

    return json_filename_list


def convert_json_or_zip_mode(args):
    json_filename_list = resolve_json_filename_list(args)

    for json_filename in json_filename_list:
        hi_json = HiJsonParser(
            json_filename,
            args.output_dir,
            args.json_export,
            set(args.json_sport_filter) if args.json_sport_filter else None,
        )
        hi_activity_list = hi_json.parse(args.from_date)
        for hi_activity in hi_activity_list:
            if args.pool_length:
                hi_activity.set_pool_length(args.pool_length)

            hi_activity.normalize_distances()

            fit_filename = build_fit_filename(args.output_dir, hi_activity)
            save_fit_file(
                hi_activity,
                save_dir=args.output_dir,
                filename_prefix=args.output_file_prefix,
                fit_filename=fit_filename,
            )

            logging.getLogger(PROGRAM_NAME).info("Converted %s", hi_activity)
