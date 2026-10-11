from inbox_triage.cli import main
from tests.helpers import EXAMPLE_CONFIG


def test_print_query_needs_no_credentials(capsys) -> None:
    exit_code = main(["--config", str(EXAMPLE_CONFIG), "--print-query"])

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("in:inbox is:unread")


def test_report_needs_no_credentials(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "report",
            "--config",
            str(EXAMPLE_CONFIG),
            "--data-dir",
            str(tmp_path / "data"),
            "--digest-dir",
            str(tmp_path / "digests"),
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.startswith("Report: ")
    report_files = list((tmp_path / "digests").glob("report-*.md"))
    assert len(report_files) == 1
    assert "## Proposals" in report_files[0].read_text(encoding="utf-8")


def test_yaml_errors_are_reported_without_traceback(tmp_path) -> None:
    import pytest

    config = tmp_path / "triage.yaml"
    config.write_text("rules:\n  - name: a category: b\n", encoding="utf-8")

    with pytest.raises(SystemExit, match=r"Invalid YAML .* at line 2, column \d+"):
        main(["--config", str(config), "--print-query"])
