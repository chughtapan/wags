"""Pytest configuration for groups E2E tests."""

import os
from collections.abc import Generator

import pytest
from fast_agent import FastAgent


@pytest.fixture
def fast_agent(request: pytest.FixtureRequest) -> Generator[FastAgent]:
    """Create FastAgent configured for groups tests."""
    test_dir = os.path.dirname(__file__)
    original_cwd = os.getcwd()
    os.chdir(test_dir)

    agent = FastAgent(
        "Groups E2E Tests",
        config_path=os.path.join(test_dir, "fastagent.config.yaml"),
        ignore_unknown_args=True,
    )

    yield agent
    os.chdir(original_cwd)
