import pytest

from hicoros.cli import create_argument_parser
from hicoros.cli import sanitize_args_string
from hicoros.hitrava import HiActivity
from hicoros.hitrava import OUTPUT_DIR


def test_create_argument_parser_accepts_json_sport_filter():
    parser = create_argument_parser(HiActivity, OUTPUT_DIR)
    args = parser.parse_args(["--json", "HiJson.json", "--json_sport_filter", "Run", "Indoor_Run"])

    assert args.json == "HiJson.json"
    assert args.json_sport_filter == ["Run", "Indoor_Run"]


def test_create_argument_parser_rejects_invalid_date():
    parser = create_argument_parser(HiActivity, OUTPUT_DIR)

    with pytest.raises(SystemExit):
        parser.parse_args(["--json", "HiJson.json", "--from_date", "2026/01/01"])


def test_create_argument_parser_has_fit_output_directory_option():
    parser = create_argument_parser(HiActivity, OUTPUT_DIR)
    args = parser.parse_args(["--json", "HiJson.json", "--output_dir", "./fit-output"])

    assert args.output_dir == "./fit-output"


def test_sanitize_args_string_masks_long_and_short_password_flags():
    args_long = "['--zip', 'HiZip.zip', '--password', 'secret123']"
    args_short = "['--zip', 'HiZip.zip', '-p', 'secret123']"

    masked_long = sanitize_args_string(args_long)
    masked_short = sanitize_args_string(args_short)

    assert "secret123" not in masked_long
    assert "secret123" not in masked_short
    assert "'--password', '********'" in masked_long
    assert "'--password', '********'" in masked_short
