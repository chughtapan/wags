"""Pytest configuration and fixtures for evaluation tests."""

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from _pytest.reports import TestReport


class _ItemWithFuncargs(Protocol):
    """Protocol for pytest Item with funcargs attribute (added at runtime)."""

    funcargs: dict[str, Any]

    def get_closest_marker(self, name: str) -> pytest.Mark | None: ...


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Configure asyncio for limited concurrency."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def model(request: pytest.FixtureRequest) -> str:
    """Model from CLI or default."""
    return cast(str, request.config.getoption("--model"))


@pytest.fixture
def temperature(request: pytest.FixtureRequest) -> float:
    """Temperature from CLI or default."""
    return cast(float, request.config.getoption("--temperature"))


@pytest.fixture
def output_dir(request: pytest.FixtureRequest) -> Path:
    """Output directory for test results."""
    path = Path(request.config.getoption("--output-dir"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom CLI options."""
    parser.addoption("--model", default="gpt-4o-mini", help="Model to use")
    parser.addoption("--temperature", default=0.001, type=float, help="Temperature for LLM (default: 0.001)")
    parser.addoption("--output-dir", default="outputs", help="Output directory for results")
    parser.addoption("--validate-only", action="store_true", help="Only validate existing logs")
    parser.addoption("--log-dir", default="outputs/raw", help="Directory with logs (for validate mode)")


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers.

    Custom markers:
    - verified_models: Marks tests that are only verified to pass with specific models.
                      Tests run for all models, but failures with unverified models
                      are converted to xfail (expected failure) instead of hard failures.
    """
    config.addinivalue_line(
        "markers", "verified_models(models): mark test to only require passing with specified models"
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any]:
    """Handle verified_models marker by converting failures to xfail for unverified models.

    This hook intercepts test results after execution. When a test marked with
    @pytest.mark.verified_models(["model1", "model2"]) fails:

    1. If the current model IS in the verified list → test fails normally (must pass)
    2. If the current model is NOT in the verified list → convert to xfail (expected)
    3. If the test passes → always passes regardless of model

    Example usage:
        @pytest.mark.verified_models(["gpt-4o", "gpt-4.1"])
        async def test_advanced_feature(model):
            # Test runs for all models via --model flag
            # But only gpt-4o and gpt-4.1 are required to pass
            ...

    Args:
        item: The pytest test item being executed
        call: The test call phase (setup, call, or teardown)

    Yields:
        The test execution outcome, potentially modified to xfail
    """
    # Let the test execute
    outcome: Any = yield
    report: TestReport = outcome.get_result()

    # Only process test execution phase (not setup/teardown) when test failed
    if report.when == "call" and report.failed:
        marker = item.get_closest_marker("verified_models")

        if marker:
            # Extract verified models list from marker args
            verified_models = marker.args[0] if marker.args else []

            # Get the current model from test fixture
            # funcargs is added by pytest at runtime to Function items
            item_with_args = cast(_ItemWithFuncargs, item)
            model = item_with_args.funcargs.get("model")

            # If current model is not in verified list, convert failure to xfail
            if model and model not in verified_models:
                report.outcome = "skipped"
                report.wasxfail = f"Model {model} not verified (verified: {', '.join(verified_models)})"
