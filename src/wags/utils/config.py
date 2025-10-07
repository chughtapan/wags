"""Configuration loading and processing for WAGS proxy servers."""

import json
import os
from pathlib import Path
from typing import Any

from fastmcp.utilities.logging import get_logger

logger = get_logger("wags.utils.config")


def _substitute_env_vars(env_dict: dict[str, Any]) -> dict[str, Any]:
    """Replace ${VAR_NAME} placeholders with environment values.

    Args:
        env_dict: Environment variables dict with potential ${VAR} placeholders

    Returns:
        Dict with environment variables substituted

    Raises:
        ValueError: If referenced environment variable is not set
    """
    result = {}
    for key, value in env_dict.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            if not var_name:  # Handle ${} case
                raise ValueError("Empty environment variable name in placeholder")
            elif var_name not in os.environ:
                raise ValueError(f"Environment variable '{var_name}' is not set")
            else:
                result[key] = os.environ[var_name]
        else:
            result[key] = value
    return result


def load_config(config_path: Path | str) -> dict[str, Any]:
    """Load and validate a WAGS server configuration file.

    Args:
        config_path: Path to JSON config file

    Returns:
        Processed config dict with env vars substituted

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If invalid JSON
        ValueError: If not exactly 1 mcpServer or missing required sections
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        config: dict[str, Any] = json.load(f)

    # Ensure single server configuration
    if "mcpServers" not in config:
        raise ValueError("Config must have 'mcpServers' section")

    servers = config.get("mcpServers", {})
    if len(servers) != 1:
        raise ValueError(f"Config must have exactly 1 mcpServer, found {len(servers)}")

    # Process env vars in the server config
    server_config = next(iter(servers.values()))
    if "env" in server_config:
        if not isinstance(server_config["env"], dict):
            raise ValueError("Server 'env' section must be a dictionary")
        server_config["env"] = _substitute_env_vars(server_config["env"])

    return config
