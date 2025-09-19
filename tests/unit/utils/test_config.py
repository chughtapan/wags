"""Unit tests for config utilities."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from wags.utils.config import create_proxy, load_config, substitute_env_vars


class TestSubstituteEnvVars:
    """Tests for substitute_env_vars function."""

    def test_substitute_in_mcp_server_env(self):
        """Test substituting environment variables in mcpServers env section."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value", "API_KEY": "secret"}):
            config = {
                "mcpServers": {
                    "test-server": {
                        "transport": "stdio",
                        "command": "test",
                        "env": {
                            "VAR1": "${TEST_VAR}",
                            "KEY": "${API_KEY}"
                        }
                    }
                }
            }
            result = substitute_env_vars(config)
            assert result["mcpServers"]["test-server"]["env"] == {
                "VAR1": "test_value",
                "KEY": "secret"
            }

    def test_no_substitution_outside_env(self):
        """Test that substitution only happens in env sections."""
        with patch.dict(os.environ, {"VAR": "value"}):
            config = {
                "mcpServers": {
                    "test": {
                        "command": "${VAR}",  # Should NOT be substituted
                        "args": ["${VAR}"],   # Should NOT be substituted
                        "env": {
                            "KEY": "${VAR}"   # Should be substituted
                        }
                    }
                },
                "other": "${VAR}"  # Should NOT be substituted
            }
            result = substitute_env_vars(config)
            assert result["mcpServers"]["test"]["command"] == "${VAR}"
            assert result["mcpServers"]["test"]["args"] == ["${VAR}"]
            assert result["mcpServers"]["test"]["env"]["KEY"] == "value"
            assert result["other"] == "${VAR}"

    def test_substitute_missing_env_var(self):
        """Test substituting missing environment variable raises error."""
        config = {
            "mcpServers": {
                "test": {
                    "env": {"KEY": "${MISSING_VAR}"}
                }
            }
        }
        with pytest.raises(ValueError, match="Environment variable 'MISSING_VAR' is not set"):
            substitute_env_vars(config)

    def test_no_mcpservers_section(self):
        """Test substitute_env_vars handles missing mcpServers gracefully."""
        config = {"key": "${VAR}", "other": "data"}
        result = substitute_env_vars(config)
        assert result == config  # No changes when no mcpServers

    def test_mixed_env_values(self):
        """Test env dict with both template and regular values."""
        with patch.dict(os.environ, {"TOKEN": "abc123"}):
            config = {
                "mcpServers": {
                    "test": {
                        "env": {
                            "TOKEN": "${TOKEN}",
                            "STATIC": "fixed_value",
                            "NUMBER": 42
                        }
                    }
                }
            }
            result = substitute_env_vars(config)
            assert result["mcpServers"]["test"]["env"] == {
                "TOKEN": "abc123",
                "STATIC": "fixed_value",
                "NUMBER": 42
            }


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_mcp_config(self):
        """Test loading a valid MCP config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "mcpServers": {
                    "test": {
                        "transport": "stdio",
                        "command": "test"
                    }
                }
            }
            json.dump(config_data, f)
            temp_path = f.name

        try:
            result = load_config(temp_path)
            assert result == config_data
        finally:
            os.unlink(temp_path)

    def test_load_no_mcpservers_raises_error(self):
        """Test loading config without mcpServers raises error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {"key": "value", "number": 42}
            json.dump(config_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Config must have 'mcpServers' section"):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)

    def test_load_multiple_servers_raises_error(self):
        """Test loading config with multiple servers raises error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "mcpServers": {
                    "server1": {"transport": "stdio", "command": "test1"},
                    "server2": {"transport": "stdio", "command": "test2"}
                }
            }
            json.dump(config_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Config must have exactly 1 mcpServer, found 2"):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)

    def test_load_empty_mcpservers_raises_error(self):
        """Test loading config with empty mcpServers raises error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {"mcpServers": {}}
            json.dump(config_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Config must have exactly 1 mcpServer, found 0"):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)

    def test_load_with_env_substitution(self):
        """Test loading config with environment variable substitution."""
        with patch.dict(os.environ, {"TEST_VAR": "substituted"}):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                config_data = {
                    "mcpServers": {
                        "test": {
                            "env": {"KEY": "${TEST_VAR}"}
                        }
                    }
                }
                json.dump(config_data, f)
                temp_path = f.name

            try:
                result = load_config(temp_path)
                assert result["mcpServers"]["test"]["env"]["KEY"] == "substituted"
            finally:
                os.unlink(temp_path)

    def test_load_nonexistent_file(self):
        """Test loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config("/nonexistent/path.json")

    def test_load_invalid_json(self):
        """Test loading invalid JSON raises JSONDecodeError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json{")
            temp_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)


class TestCreateProxy:
    """Tests for create_proxy function."""

    @patch("wags.utils.config.FastMCP.as_proxy")
    def test_create_proxy_from_dict(self, mock_as_proxy):
        """Test creating proxy from config dict."""
        mock_proxy = MagicMock()
        mock_as_proxy.return_value = mock_proxy

        config_data = {
            "mcpServers": {
                "test": {
                    "transport": "stdio",
                    "command": "test"
                }
            }
        }

        result = create_proxy(config_data, "test-proxy")

        # Check proxy was created with correct arguments
        mock_as_proxy.assert_called_once_with(
            backend=config_data,
            name="test-proxy"
        )
        assert result == mock_proxy

    @patch("wags.utils.config.FastMCP.as_proxy")
    def test_create_proxy_default_name(self, mock_as_proxy):
        """Test creating proxy with default name."""
        mock_proxy = MagicMock()
        mock_as_proxy.return_value = mock_proxy

        config_data = {"mcpServers": {"test": {}}}

        result = create_proxy(config_data)

        mock_as_proxy.assert_called_once_with(
            backend=config_data,
            name="wags-proxy"
        )
        assert result == mock_proxy


