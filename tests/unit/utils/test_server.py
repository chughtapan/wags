"""Unit tests for server utilities."""

from pathlib import Path
from unittest.mock import patch

import pytest

from wags.utils.server import run_server


@pytest.mark.asyncio
async def test_run_server_success(tmp_path: Path) -> None:
    """Test successful server execution."""
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "main.py").write_text("print('running')")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        await run_server(server_dir)
        assert mock_run.called


@pytest.mark.asyncio
async def test_run_server_missing_main(tmp_path: Path) -> None:
    """Test error when main.py missing."""
    server_dir = tmp_path / "server"
    server_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="No main.py"):
        await run_server(server_dir)


@pytest.mark.asyncio
async def test_run_server_not_directory(tmp_path: Path) -> None:
    """Test error when path not a directory."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")

    with pytest.raises(ValueError, match="must be a directory"):
        await run_server(file_path)


@pytest.mark.asyncio
async def test_run_server_failure(tmp_path: Path) -> None:
    """Test error on non-zero exit code."""
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "main.py").write_text("exit(1)")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        with pytest.raises(RuntimeError, match="exited with code 1"):
            await run_server(server_dir)
