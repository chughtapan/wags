"""Pytest configuration and fixtures for BFCL benchmark."""

from pathlib import Path

import pytest


@pytest.fixture
def output_dir(request: pytest.FixtureRequest) -> Path:
    """BFCL-specific output directory.

    Uses the global --output-dir parameter (default: outputs).
    This maintains BFCL's original behavior of writing to outputs/.
    """
    path = Path(request.config.getoption("--output-dir"))
    path.mkdir(parents=True, exist_ok=True)
    return path
