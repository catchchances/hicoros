#!/usr/bin/env python3

# Hitrava.py
# Original Work Copyright (c) 2019 Ari Cooper-Davis / Christoph Vanthuyne - github.com/aricooperdavis/Huawei-TCX-Converter
# Modified Work Copyright (c) 2019-2025 Christoph Vanthuyne - https://github.com/CTHRU/Hitrava
# Released under the Non-Profit Open Software License version 3.0

import logging

from .constants import OUTPUT_DIR
from .constants import PROGRAM_MAJOR_BUILD
from .constants import PROGRAM_MAJOR_VERSION
from .constants import PROGRAM_MINOR_BUILD
from .constants import PROGRAM_MINOR_VERSION
from .constants import PROGRAM_NAME
from .constants import PROGRAM_PATCH_VERSION
from .hi.hi_activity import HiActivity


def _init_logging(level: str = "INFO"):
    """
    Initializes the Python logging.getLogger(PROGRAM_NAME). A program specific Logger is created.

    Parameters:
    level (int): Optional - The level to which the logger will be initialized.
        Use any of the available logging.getLogger(PROGRAM_NAME).LEVEL values.
        If not specified, the default level will be set to logging.getLogger(PROGRAM_NAME).INFO

    """
    logger = logging.getLogger(PROGRAM_NAME)
    console = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(funcName)s - %(message)s")
    console.setFormatter(formatter)
    if level == "INFO":
        logger.setLevel(logging.INFO)
    elif level == "DEBUG":
        logger.setLevel(logging.DEBUG)
    logger.addHandler(console)
    logger.propagate = False


def main():
    from .cli import create_argument_parser
    from .cli import init_runtime
    from .converter import convert_json_or_zip_mode
    from .converter import convert_single_file_mode
    from .converter import convert_tar_mode

    parser = create_argument_parser(HiActivity, OUTPUT_DIR)
    args = init_runtime(
        parser,
        _init_logging,
        PROGRAM_NAME,
        (PROGRAM_MAJOR_VERSION, PROGRAM_MINOR_VERSION, PROGRAM_PATCH_VERSION, PROGRAM_MAJOR_BUILD, PROGRAM_MINOR_BUILD),
    )
    if args.file:
        convert_single_file_mode(args)
    elif args.tar:
        convert_tar_mode(args)
    elif args.json or args.zip:
        convert_json_or_zip_mode(args)


if __name__ == "__main__":
    main()
