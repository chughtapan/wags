"""Pytest configuration and fixtures for evaluation tests."""

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from _pytest.reports import TestReport


def _patch_rich_markup() -> None:
    """
    Patch fast-agent's ConsoleDisplay to disable markup parsing.

    This prevents crashes when model output contains square brackets that look like
    markup tags (e.g., [/rosout] for ROS topics, [/INST] for instruction markers).

    Background:
    - gpt-5-mini crashed on task_0010 with: MarkupError: closing tag '[/rosout]'
    - Claude crashed on task_0026 with: MarkupError: closing tag '[/INST]'

    Root cause: fast_agent/ui/console_display.py calls console.print(markup=self._markup)
    which explicitly passes markup parameter, overriding Console defaults.

    Solution: Monkey-patch ConsoleDisplay.__init__ to force _markup=False.
    """
    try:
        from fast_agent.ui.console_display import ConsoleDisplay

        # Store original __init__
        original_init = ConsoleDisplay.__init__

        def patched_init(self, *args, **kwargs):
            """Patched ConsoleDisplay.__init__ that forces _markup=False."""
            original_init(self, *args, **kwargs)
            # Override _markup attribute after initialization
            self._markup = False

        # Apply patch
        ConsoleDisplay.__init__ = patched_init
        print("[PATCH] ConsoleDisplay patched: _markup=False (prevents crashes on square brackets)")

    except ImportError:
        print("[PATCH] Warning: Could not import fast_agent.ui.console_display - Rich markup fix not applied")
    except Exception as e:
        print(f"[PATCH] Warning: Error applying Rich markup fix: {e}")


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
    parser.addoption("--output-dir", default="outputs/mcp_universe/checkpoint-2025-11-05", help="Output directory for results")
    parser.addoption("--validate-only", action="store_true", help="Only validate existing logs")
    parser.addoption("--log-dir", default="outputs/raw", help="Directory with logs (for validate mode)")
    parser.addoption("--max-workers", default=4, type=int, help="Max concurrent tests (default: 4)")


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

    # Fix Rich markup crashes when model output contains square brackets like [/rosout] or [/INST]
    # These strings appear in ROS topics and instruction markers but Rich interprets them as markup tags
    _patch_rich_markup()


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
