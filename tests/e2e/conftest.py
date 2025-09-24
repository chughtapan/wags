"""Pytest configuration for e2e tests."""

import os

import pytest
from fast_agent import FastAgent


@pytest.fixture
def fast_agent(request):
    """Create a FastAgent instance with e2e test configuration.
    
    This fixture:
    - Changes to the e2e test directory
    - Loads the fastagent.config.yaml from that directory
    - Restores the original directory after the test
    """
    # Get the e2e directory path
    test_dir = os.path.dirname(__file__)
    
    # Save original directory
    original_cwd = os.getcwd()
    
    # Change to the e2e directory
    os.chdir(test_dir)
    
    # Create agent with e2e config
    config_file = os.path.join(test_dir, "fastagent.config.yaml")
    
    agent = FastAgent(
        "E2E Test Agent",
        config_path=config_file,
        ignore_unknown_args=True,
    )
    
    # Provide the agent
    yield agent
    
    # Restore original directory
    os.chdir(original_cwd)