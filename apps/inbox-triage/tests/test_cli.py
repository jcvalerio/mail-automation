from inbox_triage.cli import main
from tests.helpers import EXAMPLE_CONFIG


def test_print_query_needs_no_credentials(capsys) -> None:
    exit_code = main(["--config", str(EXAMPLE_CONFIG), "--print-query"])

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("in:inbox is:unread")
