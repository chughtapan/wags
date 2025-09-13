"""Pytest configuration and fixtures for evaluation tests."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Configure asyncio for limited concurrency."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def model(request):
    """Model from CLI or default."""
    return request.config.getoption("--model")


@pytest.fixture
def output_dir(request):
    """Output directory for test results."""
    path = Path(request.config.getoption("--output-dir"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def pytest_addoption(parser):
    """Add custom CLI options."""
    parser.addoption("--model", default="gpt-4o-mini", help="Model to use")
    parser.addoption("--output-dir", default="outputs", help="Output directory for results")
    parser.addoption("--validate-only", action="store_true", help="Only validate existing logs")
    parser.addoption(
        "--log-dir", default="outputs/raw", help="Directory with logs (for validate mode)"
    )
    parser.addoption("--max-workers", default=4, type=int, help="Max concurrent tests (default: 4)")
