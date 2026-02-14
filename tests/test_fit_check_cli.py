from hicoros.fit.fit_self_check import FitSelfCheckReport
from hicoros.fit_check_cli import main


def test_fit_check_cli_success(monkeypatch, capsys):
    report = FitSelfCheckReport(
        fit_filename="ok.fit",
        integrity_ok=True,
        warnings=[],
        errors=[],
        message_counts={"record_mesgs": 2},
    )

    monkeypatch.setattr("sys.argv", ["hicoros-fit-check", "ok.fit"])
    monkeypatch.setattr("hicoros.fit_check_cli.check_fit_file", lambda _path: report)

    code = main()
    output = capsys.readouterr().out

    assert code == 0
    assert "Integrity: OK" in output


def test_fit_check_cli_fail_on_warning(monkeypatch, capsys):
    report = FitSelfCheckReport(
        fit_filename="warn.fit",
        integrity_ok=True,
        warnings=["w1"],
        errors=[],
        message_counts={},
    )

    monkeypatch.setattr("sys.argv", ["hicoros-fit-check", "warn.fit", "--fail-on-warning"])
    monkeypatch.setattr("hicoros.fit_check_cli.check_fit_file", lambda _path: report)

    code = main()
    output = capsys.readouterr().out

    assert code == 2
    assert "Warnings:" in output


def test_fit_check_cli_error(monkeypatch, capsys):
    report = FitSelfCheckReport(
        fit_filename="bad.fit",
        integrity_ok=False,
        warnings=[],
        errors=["e1"],
        message_counts={},
    )

    monkeypatch.setattr("sys.argv", ["hicoros-fit-check", "bad.fit"])
    monkeypatch.setattr("hicoros.fit_check_cli.check_fit_file", lambda _path: report)

    code = main()
    output = capsys.readouterr().out

    assert code == 1
    assert "Errors:" in output
