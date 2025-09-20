"""Unit tests for server template utilities."""

import pytest

from wags.utils.server_template import create_server_scaffold


class TestCreateServerScaffold:
    """Tests for create_server_scaffold function."""

    def test_creates_expected_file_structure(self, tmp_path):
        """Test scaffold creates all expected files."""
        with pytest.MonkeyPatch.context() as m:
            m.chdir(tmp_path)

            create_server_scaffold("test-server")

            server_dir = tmp_path / "servers" / "test-server"
            assert server_dir.exists()
            assert (server_dir / "__init__.py").exists()
            assert (server_dir / "handlers.py").exists()
            assert (server_dir / "main.py").exists()

    def test_uses_custom_path(self, tmp_path):
        """Test scaffold works with custom path."""
        custom_path = tmp_path / "custom" / "location"
        create_server_scaffold("my-server", custom_path)

        assert custom_path.exists()
        assert (custom_path / "__init__.py").exists()
        assert (custom_path / "handlers.py").exists()
        assert (custom_path / "main.py").exists()

    def test_generates_correct_class_names(self, tmp_path):
        """Test that generated files contain correct class names."""
        create_server_scaffold("test-server", tmp_path)

        handlers_content = (tmp_path / "handlers.py").read_text()
        main_content = (tmp_path / "main.py").read_text()

        # Verify class name generation
        assert "class Test_ServerHandlers" in handlers_content
        assert "Test_ServerHandlers()" in main_content
        assert 'if __name__ == "__main__":' in main_content
        assert "mcp.run_stdio_async()" in main_content
        assert "RequiresElicitation" in handlers_content
        assert "async def" in handlers_content

    def test_different_names_generate_correct_classes(self, tmp_path):
        """Test class name generation for various server names."""
        test_cases = [
            ("simple", "SimpleHandlers"),
            ("test-server", "Test_ServerHandlers"),
            ("my-api", "My_ApiHandlers"),
        ]

        for server_name, expected_class in test_cases:
            server_path = tmp_path / server_name
            create_server_scaffold(server_name, server_path)

            handlers_content = (server_path / "handlers.py").read_text()
            assert f"class {expected_class}" in handlers_content