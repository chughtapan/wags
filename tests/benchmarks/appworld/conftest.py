"""Pytest configuration and fixtures for AppWorld benchmark."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add AppWorld-specific CLI options."""
    parser.addoption(
        "--dataset",
        default="train",
        choices=["train", "dev", "test_normal", "test_challenge"],
        help="AppWorld dataset to use (default: train)",
    )
    parser.addoption(
        "--limit",
        default=None,
        type=int,
        help="Limit number of tasks to run (default: all)",
    )
    parser.addoption(
        "--api-mode",
        default="ground_truth",
        choices=["predicted", "ground_truth", "all"],
        help="API prediction mode: predicted (LLM), ground_truth (oracle), all (default: ground_truth)",
    )


@pytest.fixture
def appworld_dataset(request: pytest.FixtureRequest) -> str:
    """Get the AppWorld dataset name from CLI."""
    return str(request.config.getoption("--dataset"))


@pytest.fixture
def appworld_limit(request: pytest.FixtureRequest) -> int | None:
    """Get the task limit from CLI."""
    limit = request.config.getoption("--limit")
    return int(limit) if limit is not None else None


@pytest.fixture
def api_mode(request: pytest.FixtureRequest) -> str:
    """
    Get API prediction mode from CLI.

    Returns:
        "predicted": Use LLM to predict APIs (costs 1 extra call per task)
        "ground_truth": Use oracle APIs from task data (train/dev only)
        "all": Use all available APIs (limited to 20)
    """
    return str(request.config.getoption("--api-mode"))
