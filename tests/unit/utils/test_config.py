"""Unit tests for config utilities."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from wags.utils.config import _substitute_env_vars, load_config


class TestSubstituteEnvVars:
    """Tests for _substitute_env_vars function."""

    def test_substitute_env_vars(self):
        """Test substituting environment variables in env dict."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value", "API_KEY": "secret"}):
            env_dict = {
                "VAR1": "${TEST_VAR}",
                "KEY": "${API_KEY}"
            }
            result = _substitute_env_vars(env_dict)
            assert result == {
                "VAR1": "test_value",
                "KEY": "secret"
            }

    def test_substitute_missing_env_var(self):
        """Test substituting missing environment variable raises error."""
        env_dict = {"KEY": "${MISSING_VAR}"}
        with pytest.raises(ValueError, match="Environment variable 'MISSING_VAR' is not set"):
            _substitute_env_vars(env_dict)

    def test_no_substitution_needed(self):
        """Test env dict with no substitution placeholders."""
        env_dict = {"STATIC": "value", "NUMBER": 42}
        result = _substitute_env_vars(env_dict)
        assert result == env_dict

    def test_mixed_env_values(self):
        """Test env dict with both template and regular values."""
        with patch.dict(os.environ, {"TOKEN": "abc123"}):
            env_dict = {
                "TOKEN": "${TOKEN}",
                "STATIC": "fixed_value",
                "NUMBER": 42
            }
            result = _substitute_env_vars(env_dict)
            assert result == {
                "TOKEN": "abc123",
                "STATIC": "fixed_value",
                "NUMBER": 42
            }

    def test_empty_env_dict(self):
        """Test empty env dict returns empty dict."""
        result = _substitute_env_vars({})
        assert result == {}

    def test_malformed_placeholder(self):
        """Test that malformed placeholders are left unchanged."""
        env_dict = {
            "BAD1": "${INCOMPLETE",
            "BAD2": "MISSING_BRACE}",
            "GOOD": "normal_value"
        }
        result = _substitute_env_vars(env_dict)
        assert result == env_dict  # All values unchanged since none are proper ${VAR} format

    def test_empty_placeholder(self):
        """Test that empty placeholder raises error."""
        env_dict = {"BAD": "${}"}
        with pytest.raises(ValueError, match="Empty environment variable name in placeholder"):
            _substitute_env_vars(env_dict)


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

    def test_load_invalid_env_section(self):
        """Test loading config with non-dict env section raises error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "mcpServers": {
                    "test": {
                        "command": "test",
                        "env": "not_a_dict"  # Invalid - should be dict
                    }
                }
            }
            json.dump(config_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Server 'env' section must be a dictionary"):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)
