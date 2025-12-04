"""Pytest configuration and fixtures for AppWorld benchmark."""

from pathlib import Path

import pytest


@pytest.fixture
def output_dir(request: pytest.FixtureRequest) -> Path:
    """AppWorld-specific output directory.

    Overrides the global output_dir fixture to write directly to
    results/{model}/{dataset}/outputs/ for organized storage.
    """
    model = str(request.config.getoption("--model"))
    dataset = str(request.config.getoption("--dataset"))

    # Write directly to results directory
    path = Path("results") / model / dataset / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
        default="app_oracle",
        choices=["predicted", "ground_truth", "app_oracle", "all"],
        help=(
            "API prediction mode: predicted (LLM), ground_truth (API-level oracle), "
            "app_oracle (app-level oracle), all (default: ground_truth)"
        ),
    )
    parser.addoption(
        "--experiment-dir",
        default=None,
        type=str,
        help=(
            "Experiment directory name (e.g., 'gpt-5/train' or 'claude-sonnet-4-5/dev'). "
            "If not specified, auto-generates timestamp-based name. "
            "Results will be saved to experiments/outputs/{experiment-dir}/"
        ),
    )
    parser.addoption(
        "--start-from",
        default=None,
        type=str,
        help=(
            "Start from specified task_id (skip all tests before it). "
            "Example: --start-from 692c77d_1. Useful for resuming interrupted benchmark runs."
        ),
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
        "ground_truth": Use oracle APIs from task data (API-level oracle, train/dev only)
        "app_oracle": Use oracle to identify apps, load all APIs from those apps (app-level oracle)
        "all": Use all available APIs (no limit)
    """
    return str(request.config.getoption("--api-mode"))


@pytest.fixture(scope="session")
def experiment_name(request: pytest.FixtureRequest) -> str:
    """
    Get or generate experiment directory name for the test session.

    All tests in this session will write to the same experiment directory,
    organized by task_id in subdirectories: experiments/outputs/{experiment_name}/tasks/{task_id}/

    Automatically uses {model}/{dataset} pattern for organized experiment tracking.
    """

    experiment_dir = request.config.getoption("--experiment-dir", None)

    if experiment_dir:
        # Use specified experiment directory
        return str(experiment_dir)
    else:
        # Use model/dataset pattern for organized experiment tracking
        # This works for both normal runs and validation
        model = str(request.config.getoption("--model"))
        dataset = str(request.config.getoption("--dataset"))
        return f"{model}/{dataset}"
