"""Server utilities for WAGS CLI."""

import os
import subprocess
import sys
from pathlib import Path

from fastmcp.utilities.logging import get_logger

logger = get_logger("wags.utils.server")


async def run_server(server_path: Path):
    """Run a server directly as a Python script.

    Args:
        server_path: Path to the server directory containing main.py
    """
    if not server_path.exists():
        raise FileNotFoundError(f"Server directory not found: {server_path}")

    if not server_path.is_dir():
        raise ValueError(f"Path must be a directory: {server_path}")

    main_path = server_path / "main.py"
    if not main_path.exists():
        raise FileNotFoundError(f"No main.py found in {server_path}")

    logger.info(f"Running server from {server_path}")

    # Run the server script directly with proper environment
    result = subprocess.run(
        [sys.executable, str(main_path)],
        check=False, cwd=str(server_path),
        env=os.environ.copy()
    )

    if result.returncode != 0:
        raise RuntimeError(f"Server exited with code {result.returncode}")