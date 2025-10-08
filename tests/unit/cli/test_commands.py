"""Unit tests for CLI command error handling."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from wags.cli.main import quickstart, start_server


@patch("wags.utils.server.run_server")
@patch("wags.cli.main.logger")
@patch("wags.cli.main.sys.exit")
def test_start_server_command_handles_errors(mock_exit: Any, mock_logger: Any, mock_run_server: Any) -> None:
    """Test start-server command handles errors gracefully."""
    mock_run_server.side_effect = Exception("Server startup failed")

    start_server(Path("test-server"))

    mock_logger.error.assert_called_once()
    mock_exit.assert_called_once_with(1)


@patch("wags.utils.config.load_config")
@patch("wags.cli.main.logger")
@patch("wags.cli.main.sys.exit")
def test_quickstart_command_handles_errors(mock_exit: Any, mock_logger: Any, mock_load_config: Any) -> None:
    """Test quickstart command handles errors gracefully."""
    mock_load_config.side_effect = Exception("Failed to load config")

    quickstart(Path("test-config.json"))

    mock_logger.error.assert_called_once()
    mock_exit.assert_called_once_with(1)
