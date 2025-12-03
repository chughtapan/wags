"""Pytest configuration for humanity test experiment."""

import pytest

_BENCHMARKS = [
    "bfcl",
    "appworld_train",
    "appworld_dev",
    "appworld_test_normal",
    "appworld_test_challenge",
    "mcp_universe",
]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add humanity test CLI options."""
    parser.addoption(
        "--benchmarks",
        action="append",
        default=[],
        help=f"Benchmark(s) to use, can specify multiple (choices: {', '.join(_BENCHMARKS)})",
    )
    parser.addoption(
        "--limit",
        default=None,
        type=int,
        help="Limit number of tasks per benchmark (default: all)",
    )
