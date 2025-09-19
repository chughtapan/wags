"""Centralized configuration utilities for WAGS."""

import json
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

logger = get_logger("wags.utils.config")


def substitute_env_vars(config: dict[str, Any]) -> dict[str, Any]:
    """Substitute environment variables in MCP server configs.

    Only processes env sections within mcpServers.
    Environment variables should be in format ${VAR_NAME}.

    Args:
        config: Configuration dict with mcpServers section

    Returns:
        Configuration with environment variables substituted in env sections
    """
    result = config.copy()
    servers = result.get("mcpServers", {})

    for server_config in servers.values():
        if isinstance(server_config, dict) and "env" in server_config:
            env_dict = server_config["env"]
            if isinstance(env_dict, dict):
                processed_env = {}
                for key, value in env_dict.items():
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        var_name = value[2:-1]
                        if var_name not in os.environ:
                            raise ValueError(f"Environment variable '{var_name}' is not set")
                        processed_env[key] = os.environ[var_name]
                    else:
                        processed_env[key] = value
                server_config["env"] = processed_env

    return result


def load_config(config_path: Path | str) -> dict[str, Any]:
    """Load a JSON config file and substitute environment variables.

    Args:
        config_path: Path to the JSON config file

    Returns:
        Loaded and processed configuration dict

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is invalid JSON
        ValueError: If config doesn't have exactly 1 mcpServer
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    # Validate config structure
    if "mcpServers" not in config:
        raise ValueError("Config must have 'mcpServers' section")

    servers = config.get("mcpServers", {})
    if len(servers) != 1:
        raise ValueError(f"Config must have exactly 1 mcpServer, found {len(servers)}")

    return substitute_env_vars(config)


def create_proxy(
    config: dict[str, Any],
    server_name: str = "wags-proxy"
) -> FastMCP:
    """Create a FastMCP proxy server from a validated config dict.

    Args:
        config: Validated configuration dict with mcpServers section
        server_name: Name for the proxy server

    Returns:
        FastMCP proxy instance ready for middleware addition
    """
    mcp = FastMCP.as_proxy(
        backend=config,
        name=server_name
    )
    logger.debug(f"Created proxy server '{server_name}'")
    return mcp