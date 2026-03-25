from unittest.mock import patch

from click.testing import CliRunner

from eliis_downloader.cli import main


def test_cli_dry_run():
    runner = CliRunner()
    with patch("eliis_downloader.cli.run") as mock_run:
        result = runner.invoke(main, ["./photos", "--email", "test@example.com", "--password", "pass", "--dry-run"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args
    assert call_kwargs.kwargs["dry_run"] is True
    assert call_kwargs.kwargs["include_absent"] is False


def test_cli_include_absent():
    runner = CliRunner()
    with patch("eliis_downloader.cli.run") as mock_run:
        result = runner.invoke(main, ["./photos", "--email", "t@e.com", "--password", "p", "--include-absent"])
    assert result.exit_code == 0
    assert mock_run.call_args.kwargs["include_absent"] is True


def test_cli_child_filter():
    runner = CliRunner()
    with patch("eliis_downloader.cli.run") as mock_run:
        result = runner.invoke(main, ["./photos", "--email", "t@e.com", "--password", "p", "--child", "Alice"])
    assert result.exit_code == 0
    assert mock_run.call_args.kwargs["child_filter"] == "Alice"
