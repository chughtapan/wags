"""Integration tests for WAGS CLI commands."""

import importlib.util
import sys
from pathlib import Path

import pytest
from fastmcp import Client


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to integration test fixtures."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def working_dir(tmp_path: Path, fixtures_dir: Path) -> Path:
    """Create a working directory with test server and config."""
    import json

    # Copy server.py to working dir
    server_src = fixtures_dir / "server.py"
    server_dst = tmp_path / "server.py"
    server_dst.write_text(server_src.read_text())

    # Create config with absolute path to server
    config_data = {
        "mcpServers": {
            "test": {
                "command": sys.executable,
                "args": [str(server_dst)],
            }
        }
    }
    config_dst = tmp_path / "config.json"
    config_dst.write_text(json.dumps(config_data, indent=2))

    return tmp_path


class TestQuickstartCommand:
    """Test the quickstart CLI command."""

    def test_quickstart_generates_files(self, working_dir: Path) -> None:
        """Test quickstart generates handlers and main files."""
        from wags.cli.main import quickstart

        config_path = working_dir / "config.json"
        quickstart(config_path, force=True)

        handlers_path = working_dir / "handlers.py"
        main_path = working_dir / "main.py"

        assert handlers_path.exists()
        assert main_path.exists()

        # Verify handlers content
        handlers_content = handlers_path.read_text()
        assert "class Handlers:" in handlers_content
        assert "async def echo" in handlers_content
        assert "async def add" in handlers_content

        # Verify main content
        main_content = main_path.read_text()
        assert "from handlers import Handlers" in main_content
        assert "load_config" in main_content
        assert "create_proxy" in main_content

    async def test_generated_server_works(self, working_dir: Path) -> None:
        """Test that generated main.py creates a working proxy server."""
        from wags.cli.main import quickstart

        config_path = working_dir / "config.json"
        quickstart(config_path, force=True)

        # Import generated modules
        sys.path.insert(0, str(working_dir))
        try:
            # Import handlers
            handlers_spec = importlib.util.spec_from_file_location("handlers", working_dir / "handlers.py")
            assert handlers_spec and handlers_spec.loader
            handlers_module = importlib.util.module_from_spec(handlers_spec)
            handlers_spec.loader.exec_module(handlers_module)

            # Import main
            main_spec = importlib.util.spec_from_file_location("main", working_dir / "main.py")
            assert main_spec and main_spec.loader
            main_module = importlib.util.module_from_spec(main_spec)
            main_spec.loader.exec_module(main_module)

            # Test the proxy server
            mcp_proxy = main_module.mcp
            async with Client(mcp_proxy) as client:
                tools = await client.list_tools()
                tool_names = [tool.name for tool in tools]

                assert "echo" in tool_names
                assert "add" in tool_names

                # Verify tools work
                result = await client.call_tool("add", {"a": 5, "b": 3})
                assert result.data == 8

        finally:
            sys.path.remove(str(working_dir))

    def test_quickstart_only_handlers(self, working_dir: Path) -> None:
        """Test quickstart --only-handlers flag."""
        from wags.cli.main import quickstart

        config_path = working_dir / "config.json"
        quickstart(config_path, only_handlers=True, force=True)

        assert (working_dir / "handlers.py").exists()
        assert not (working_dir / "main.py").exists()

    def test_quickstart_custom_class_name(self, working_dir: Path) -> None:
        """Test quickstart with custom class name."""
        from wags.cli.main import quickstart

        config_path = working_dir / "config.json"
        quickstart(config_path, class_name="CustomHandlers", force=True)

        handlers_content = (working_dir / "handlers.py").read_text()
        assert "class CustomHandlers:" in handlers_content

        main_content = (working_dir / "main.py").read_text()
        assert "from handlers import CustomHandlers" in main_content
        assert "CustomHandlers()" in main_content
