"""Pytest configuration and fixtures for AppWorld benchmark."""

from pathlib import Path

import pytest

VALID_DATASETS = {"train", "dev", "test_normal", "test_challenge"}


@pytest.fixture
def output_dir(request: pytest.FixtureRequest) -> Path:
    """AppWorld output directory.

    Uses --output-dir if specified, otherwise auto-infers as
    results/{experiment_name}/outputs/
    """
    output_dir_opt = str(request.config.getoption("--output-dir"))

    # If not default "outputs", use the specified path directly
    if output_dir_opt != "outputs":
        path = Path(output_dir_opt)
    else:
        # Use experiment_name for consistent directory structure
        exp_name = get_experiment_name(request.config)
        path = Path("results") / exp_name / "outputs"

    path.mkdir(parents=True, exist_ok=True)
    return path


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add AppWorld-specific CLI options."""
    parser.addoption(
        "--datasets",
        default="train,dev",
        help="Comma-separated AppWorld datasets: train,dev,test_normal,test_challenge (default: train,dev)",
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
        "--start-from",
        default=None,
        type=str,
        help=(
            "Start from specified task_id (skip all tests before it). "
            "Example: --start-from 692c77d_1. Useful for resuming interrupted benchmark runs."
        ),
    )
    parser.addoption(
        "--default-few-shot",
        action="store_true",
        default=False,
        help="Include few-shot examples in system prompt (default: zero-shot, no examples)",
    )
    parser.addoption(
        "--appworld-experiment-name",
        default=None,
        type=str,
        help="Experiment name for AppWorld data (default: auto-inferred as {model}/{datasets})",
    )


def parse_datasets(datasets_str: str) -> list[str]:
    """Parse comma-separated datasets string and validate."""
    datasets = [d.strip() for d in datasets_str.split(",") if d.strip()]
    invalid = set(datasets) - VALID_DATASETS
    if invalid:
        raise ValueError(f"Invalid datasets: {invalid}. Valid options: {VALID_DATASETS}")
    return datasets


def get_datasets_dir(datasets_str: str) -> str:
    """Parse datasets and return underscore-joined directory name."""
    datasets = parse_datasets(datasets_str)
    return "_".join(datasets)


def get_experiment_name(config: pytest.Config) -> str:
    """Get experiment name from config (helper for use outside fixtures)."""
    name = config.getoption("--appworld-experiment-name", None)
    if name:
        return str(name)

    # Auto-infer from model/datasets
    model = str(config.getoption("--model"))
    datasets_str = str(config.getoption("--datasets"))
    datasets_dir = get_datasets_dir(datasets_str)
    return f"{model}/{datasets_dir}"


@pytest.fixture
def appworld_datasets(request: pytest.FixtureRequest) -> list[str]:
    """Get the AppWorld dataset names from CLI."""
    datasets_str = str(request.config.getoption("--datasets"))
    return parse_datasets(datasets_str)


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


@pytest.fixture
def use_few_shot(request: pytest.FixtureRequest) -> bool:
    """
    Get few-shot mode from CLI.

    Returns:
        True if --default-few-shot flag is set (include examples in prompt)
        False by default (zero-shot, no examples)
    """
    return bool(request.config.getoption("--default-few-shot"))


@pytest.fixture(scope="session")
def experiment_name(request: pytest.FixtureRequest) -> str:
    """
    Experiment name for AppWorld evaluation data.

    AppWorld saves to: experiments/outputs/{experiment_name}/tasks/{task_id}/
    Results saved to: results/{experiment_name}/outputs/
    Can be specified via --appworld-experiment-name or auto-inferred as {model}/{datasets}.
    """
    return get_experiment_name(request.config)
