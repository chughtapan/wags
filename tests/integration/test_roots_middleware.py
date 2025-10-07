"""Integration tests for RootsMiddleware with FastMCP."""

from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from mcp.client.session import ClientSession
from mcp.shared.context import RequestContext

from wags import create_proxy
from wags.middleware.roots import RootsMiddleware, requires_root


class TestHandlers:
    """Test handlers with root-protected methods."""

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_issue(self, owner: str, repo: str, title: str) -> dict[str, Any]:
        """Create an issue in a GitHub repository."""
        return {"created": f"issue '{title}' in {owner}/{repo}"}

    @requires_root("https://github.com/{owner}/{repo}")
    async def delete_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Delete a GitHub repository."""
        return {"deleted": f"{owner}/{repo}"}

    @requires_root("https://api.example.com/{endpoint}")
    async def call_api(self, endpoint: str, data: str) -> dict[str, Any]:
        """Call an API endpoint."""
        return {"called": endpoint, "data": data}

    async def unprotected_method(self, data: str) -> dict[str, Any]:
        """Method without root protection."""
        return {"data": data, "protected": False}


@pytest.mark.asyncio
class TestRootsMiddlewareIntegration:
    """Integration tests for RootsMiddleware."""

    async def test_roots_validation_allows_matching_literal(self) -> None:
        """Test that literal root prefixes allow matching resources."""
        # Create server with middleware
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        # Register tools - directly use the handlers methods
        mcp.tool(handlers.create_issue)

        # Test with client
        async with Client(mcp, roots=["https://github.com/myorg/"]) as client:
            # Should allow resources under myorg
            result = await client.call_tool(
                "create_issue", {"owner": "myorg", "repo": "test-repo", "title": "Test Issue"}
            )
            assert result.data["created"] == "issue 'Test Issue' in myorg/test-repo"

            # Should deny resources under other orgs
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("create_issue", {"owner": "other-org", "repo": "test", "title": "Test"})
            assert "Access denied" in str(exc_info.value)

    async def test_roots_validation_with_org_prefix(self) -> None:
        """Test that concrete org prefix allows all repos in that org."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        @mcp.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return await handlers.create_issue(owner, repo, title)

        # Use concrete prefix for myorg
        async with Client(mcp, roots=["https://github.com/myorg/"]) as client:
            # Should allow any repo in myorg
            result = await client.call_tool("create_issue", {"owner": "myorg", "repo": "repo1", "title": "Test"})
            assert "myorg/repo1" in result.data["created"]

            result = await client.call_tool("create_issue", {"owner": "myorg", "repo": "repo2", "title": "Test"})
            assert "myorg/repo2" in result.data["created"]

            # Should deny other orgs
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("create_issue", {"owner": "other-org", "repo": "repo1", "title": "Test"})
            assert "Access denied" in str(exc_info.value)

    async def test_roots_change_notification_updates_validation(self) -> None:
        """Test that roots change notification updates the validation rules."""
        # Create a backend server with the tool
        backend = FastMCP("backend-server")
        handlers = TestHandlers()

        @backend.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return await handlers.create_issue(owner, repo, title)

        # Create proxy using our create_proxy method
        # We need to create a config that points to the backend
        mcp = create_proxy(backend, server_name="test-proxy")
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        # Use a dynamic roots handler that can be changed
        current_roots = ["https://github.com/org1/"]

        async def dynamic_roots_handler(context: RequestContext[ClientSession, Any]) -> list[str]:
            """Return current roots dynamically."""
            return current_roots

        # Start with dynamic roots handler
        async with Client(mcp, roots=dynamic_roots_handler) as client:
            # Initial call to org1 succeeds
            result = await client.call_tool("create_issue", {"owner": "org1", "repo": "repo", "title": "Test"})
            assert "org1/repo" in result.data["created"]

            # org2 fails initially
            with pytest.raises(Exception):
                await client.call_tool("create_issue", {"owner": "org2", "repo": "repo", "title": "Test"})

            # Change roots to org2
            current_roots.clear()
            current_roots.append("https://github.com/org2/")
            await client.send_roots_list_changed()

            # Now org1 should fail
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("create_issue", {"owner": "org1", "repo": "repo", "title": "Test"})
            assert "Access denied" in str(exc_info.value)

            # And org2 should work
            result = await client.call_tool("create_issue", {"owner": "org2", "repo": "repo", "title": "Test"})
            assert "org2/repo" in result.data["created"]

    async def test_empty_roots_fails_closed(self) -> None:
        """Test that empty roots list (with capability) fails closed."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        @mcp.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return await handlers.create_issue(owner, repo, title)

        # Client WITH roots capability but empty list
        async with Client(mcp, roots=[]) as client:
            # Should deny all protected calls
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("create_issue", {"owner": "any", "repo": "repo", "title": "Test"})
            assert "No roots configured" in str(exc_info.value)

    async def test_unprotected_methods_bypass_validation(self) -> None:
        """Test that methods without @requires_root work regardless of roots."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        @mcp.tool
        async def unprotected_method(data: str) -> dict[str, Any]:
            return await handlers.unprotected_method(data)

        # Client without roots
        async with Client(mcp) as client:
            # Unprotected method should work
            result = await client.call_tool("unprotected_method", {"data": "test data"})
            assert result.data["data"] == "test data"
            assert result.data["protected"] is False

    async def test_multiple_roots_any_match_allows(self) -> None:
        """Test that any matching root in the list allows access."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        @mcp.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return await handlers.create_issue(owner, repo, title)

        @mcp.tool
        async def call_api(endpoint: str, data: str) -> dict[str, Any]:
            return await handlers.call_api(endpoint, data)

        # Multiple roots for different services
        roots = ["https://github.com/allowed-org/", "https://api.example.com/v1/", "https://api.example.com/v2/"]

        async with Client(mcp, roots=roots) as client:
            # GitHub root works
            result = await client.call_tool("create_issue", {"owner": "allowed-org", "repo": "test", "title": "Test"})
            assert "allowed-org/test" in result.data["created"]

            # API v1 works
            result = await client.call_tool("call_api", {"endpoint": "v1/users", "data": "test"})
            assert result.data["called"] == "v1/users"

            # API v2 works
            result = await client.call_tool("call_api", {"endpoint": "v2/users", "data": "test"})
            assert result.data["called"] == "v2/users"

            # Unallowed paths fail
            with pytest.raises(Exception):
                await client.call_tool("call_api", {"endpoint": "v3/users", "data": "test"})

    async def test_specific_repo_root(self) -> None:
        """Test that a specific repo root allows only that repo."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        @mcp.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return await handlers.create_issue(owner, repo, title)

        @mcp.tool
        async def delete_repo(owner: str, repo: str) -> dict[str, Any]:
            return await handlers.delete_repo(owner, repo)

        # Root for specific repo only
        async with Client(mcp, roots=["https://github.com/myorg/specific-repo"]) as client:
            # Should allow operations on specific-repo
            result = await client.call_tool(
                "create_issue", {"owner": "myorg", "repo": "specific-repo", "title": "Test"}
            )
            assert "myorg/specific-repo" in result.data["created"]

            # Should allow other operations on same repo
            result = await client.call_tool("delete_repo", {"owner": "myorg", "repo": "specific-repo"})
            assert result.data["deleted"] == "myorg/specific-repo"

            # Should deny other repos in same org
            with pytest.raises(Exception):
                await client.call_tool("create_issue", {"owner": "myorg", "repo": "other-repo", "title": "Test"})

    async def test_multiple_org_prefix_roots(self) -> None:
        """Test multiple concrete org prefixes."""
        mcp = FastMCP("test-server")
        handlers = TestHandlers()
        mcp.add_middleware(RootsMiddleware(handlers=handlers))

        @mcp.tool
        async def create_issue(owner: str, repo: str, title: str) -> dict[str, Any]:
            return await handlers.create_issue(owner, repo, title)

        # Multiple concrete org prefixes
        roots = [
            "https://github.com/public/",  # All public org repos
            "https://github.com/partner/",  # All partner org repos
        ]

        async with Client(mcp, roots=roots) as client:
            # Public org prefix works
            result = await client.call_tool("create_issue", {"owner": "public", "repo": "any-repo", "title": "Test"})
            assert "public/any-repo" in result.data["created"]

            # Partner org prefix works
            result = await client.call_tool("create_issue", {"owner": "partner", "repo": "specific", "title": "Test"})
            assert "partner/specific" in result.data["created"]

            # Non-matching fails
            with pytest.raises(Exception):
                await client.call_tool("create_issue", {"owner": "private", "repo": "repo", "title": "Test"})
