"""Integration tests for WAGS CLI workflow."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import Tool

from wags.utils.middleware_generator import generate_middleware_stub
from wags.utils.server import import_server_module
from wags.utils.server_template import create_server_scaffold


class TestCLIIntegration:
    """End-to-end tests for WAGS CLI workflow."""

    def test_full_server_creation_workflow(self, tmp_path):
        """Test creating a new server from scratch."""
        # Change to temp directory
        with pytest.MonkeyPatch.context() as m:
            m.chdir(tmp_path)

            # Step 1: Create a new server scaffold
            server_name = "test-integration"
            create_server_scaffold(server_name)

            # Verify server was created
            server_path = tmp_path / "servers" / server_name
            assert server_path.exists()
            # Note: config.json is no longer created automatically
            assert (server_path / "middleware.py").exists()
            assert (server_path / "main.py").exists()
            assert (server_path / "__init__.py").exists()

            # Step 2: Create config manually (no longer auto-created)
            config = {
                "mcpServers": {
                    server_name: {
                        "transport": "stdio",
                        "command": "echo",
                        "args": ["test"]
                    }
                }
            }
            config_path = server_path / "config.json"
            config_path.write_text(json.dumps(config, indent=2))

            # Step 3: Verify middleware structure
            middleware_content = (server_path / "middleware.py").read_text()
            assert "ElicitationMiddleware" in middleware_content
            assert "@tool_handler" in middleware_content
            assert "Test_IntegrationMiddleware" in middleware_content

            # Step 4: Verify main.py structure
            main_content = (server_path / "main.py").read_text()
            assert "load_config" in main_content
            assert "create_proxy" in main_content
            assert "__mcp__ = mcp" in main_content
            assert "Test_IntegrationMiddleware" in main_content

    @pytest.mark.asyncio
    async def test_stub_generation_workflow(self, tmp_path):
        """Test generating middleware stubs from an MCP server."""
        # Create a mock config
        config_path = tmp_path / "test_config.json"
        config_data = {
            "mcpServers": {
                "test-server": {
                    "transport": "stdio",
                    "command": "echo",
                    "args": ["test"]
                }
            }
        }
        config_path.write_text(json.dumps(config_data))

        # Mock the Client to return test tools
        mock_tools = [
            Tool(
                name="create_item",
                description="Create a new item",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": "integer"}
                    },
                    "required": ["name"]
                }
            ),
            Tool(
                name="delete_item",
                description="Delete an item",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"}
                    },
                    "required": ["id"]
                }
            )
        ]

        with patch("wags.utils.middleware_generator.Client") as mock_client:
            mock_mcp = AsyncMock()
            mock_mcp.list_tools = AsyncMock(return_value=mock_tools)
            mock_mcp.__aenter__ = AsyncMock(return_value=mock_mcp)
            mock_mcp.__aexit__ = AsyncMock()
            mock_client.return_value = mock_mcp

            # Generate stub
            output_path = tmp_path / "generated_middleware.py"
            await generate_middleware_stub(
                config_path,
                server_name="test-server",
                output_path=output_path,
                class_name="TestGeneratedMiddleware"
            )

            # Verify generated code
            assert output_path.exists()
            generated_content = output_path.read_text()

            # Check class definition
            assert "class TestGeneratedMiddleware(ElicitationMiddleware):" in generated_content

            # Check generated methods
            assert "async def create_item(" in generated_content
            assert "name: str" in generated_content
            assert "quantity: int | None = None" in generated_content

            assert "async def delete_item(" in generated_content
            assert "id: str" in generated_content

            # Check decorators and docstrings
            assert "@tool_handler" in generated_content
            assert '"""Create a new item"""' in generated_content
            assert '"""Delete an item"""' in generated_content

    def test_server_discovery_and_import(self, tmp_path):
        """Test discovering and importing a server module."""
        # Create a server structure
        server_name = "discovery-test"
        server_path = tmp_path / "servers" / server_name
        create_server_scaffold(server_name, server_path)

        # Discovery no longer exists - use explicit paths

        # Modify main.py to have testable content
        main_content = '''
"""Test server main."""
from unittest.mock import MagicMock
__mcp__ = MagicMock()
__mcp__.__class__.__name__ = "FastMCP"
'''
        (server_path / "main.py").write_text(main_content)

        # Test import (with mocked FastMCP check)
        with patch("wags.utils.server.isinstance") as mock_isinstance:
            mock_isinstance.return_value = True
            module = import_server_module(server_path)
            assert module is not None
            assert hasattr(module, "__class__")

    def test_multiple_server_workflow(self, tmp_path):
        """Test managing multiple servers."""
        with pytest.MonkeyPatch.context() as m:
            m.chdir(tmp_path)

            # Create multiple servers
            servers = ["auth-server", "data-server", "api-gateway"]
            for server in servers:
                create_server_scaffold(server)

            # Verify all servers were created
            for server in servers:
                server_path = tmp_path / "servers" / server
                assert server_path.exists()

                # Check each has unique middleware class
                middleware_content = (server_path / "middleware.py").read_text()
                class_name = server.replace("-", "_").title() + "Middleware"
                assert f"class {class_name}" in middleware_content

    @pytest.mark.asyncio
    async def test_config_with_env_vars(self, tmp_path):
        """Test that environment variables are properly substituted."""
        import os

        # Set test environment variable
        os.environ["TEST_API_KEY"] = "secret_key_123"

        try:
            # Create server with env var in config
            server_path = tmp_path / "env-test"
            server_path.mkdir(parents=True)

            config_data = {
                "mcpServers": {
                    "env-test": {
                        "transport": "stdio",
                        "command": "test",
                        "env": {
                            "API_KEY": "${TEST_API_KEY}"
                        }
                    }
                }
            }

            config_path = server_path / "config.json"
            config_path.write_text(json.dumps(config_data))

            # Test loading config with env substitution
            from wags.utils.config import load_config
            loaded = load_config(config_path)

            # Verify env var was substituted
            assert loaded["mcpServers"]["env-test"]["env"]["API_KEY"] == "secret_key_123"

        finally:
            # Clean up env var
            del os.environ["TEST_API_KEY"]

    def test_error_handling_workflow(self, tmp_path):
        """Test error handling in various scenarios."""
        with pytest.MonkeyPatch.context() as m:
            m.chdir(tmp_path)

            # Test running non-existent server path
            # (discover_server no longer exists - use explicit paths)

            # Test importing server without main.py
            empty_server = tmp_path / "empty-server"
            empty_server.mkdir()
            with pytest.raises(FileNotFoundError, match="No main.py"):
                import_server_module(empty_server)

            # Test importing server without __mcp__ export
            bad_server = tmp_path / "bad-server"
            bad_server.mkdir()
            (bad_server / "main.py").write_text("# No __mcp__ export")
            with pytest.raises(AttributeError, match="__mcp__"):
                import_server_module(bad_server)