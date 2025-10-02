"""Pytest configuration for todo e2e tests."""

import os

import pytest
from fast_agent import FastAgent


@pytest.fixture
def fast_agent(request):
    """Create a FastAgent instance with todo test configuration.

    This fixture:
    - Changes to the todos test directory
    - Loads the fastagent.config.yaml from that directory
    - Restores the original directory after the test
    """
    test_dir = os.path.dirname(__file__)
    original_cwd = os.getcwd()

    # Change to todos directory so relative paths work
    os.chdir(test_dir)

    # Create agent with todos config
    config_file = os.path.join(test_dir, "fastagent.config.yaml")

    agent = FastAgent(
        "Todo E2E Tests",
        config_path=config_file,
        ignore_unknown_args=True,
    )

    yield agent

    os.chdir(original_cwd)
