import argparse
import sys

from hicoros.fit.fit_self_check import check_fit_file


def main():
    parser = argparse.ArgumentParser(description="FIT post-export self-check")
    parser.add_argument("fit_file", help="Path to a .fit file")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit with code 2 when warnings are found")
    args = parser.parse_args()

    report = check_fit_file(args.fit_file)

    print(f"File: {report.fit_filename}")
    print(f"Integrity: {'OK' if report.integrity_ok else 'FAILED'}")
    if report.message_counts:
        count_text = ", ".join(f"{name}={count}" for name, count in sorted(report.message_counts.items()))
        print(f"Messages: {count_text}")

    if report.errors:
        print("Errors:")
        for err in report.errors:
            print(f"- {err}")

    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning}")

    if report.errors:
        return 1
    if report.warnings and args.fail_on_warning:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
