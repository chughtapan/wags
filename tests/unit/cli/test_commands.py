"""Unit tests for CLI command error handling."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from wags.cli.main import init, run


@patch("wags.utils.server.run_server")
@patch("wags.cli.main.logger")
@patch("wags.cli.main.sys.exit")
def test_run_command_handles_errors(mock_exit: Any, mock_logger: Any, mock_run_server: Any) -> None:
    """Test run command handles errors gracefully."""
    # Mock run_server as an async function that raises an exception
    mock_run_server.side_effect = Exception("Server startup failed")

    run(Path("test-server"))

    mock_logger.error.assert_called_once()
    mock_exit.assert_called_once_with(1)


@patch("wags.cli.main.console")
@patch("wags.cli.main.logger")
@patch("wags.cli.main.sys.exit")
def test_init_command_handles_errors(mock_exit: Any, mock_logger: Any, mock_console: Any) -> None:
    """Test init command handles errors gracefully."""
    with patch("wags.utils.server_template.create_server_scaffold") as mock_scaffold:
        mock_scaffold.side_effect = Exception("Failed to create scaffold")

        init("test-server", path=None)

        mock_logger.error.assert_called_once()
        mock_exit.assert_called_once_with(1)
