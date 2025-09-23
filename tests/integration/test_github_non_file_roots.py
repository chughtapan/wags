"""End-to-end integration test for non-file roots with GitHub server and fast-agent."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
from fast_agent import FastAgent
from fastmcp import FastMCP
from fastmcp.client import Client

from wags import create_proxy
from wags.middleware.roots import RootsMiddleware, requires_root


class MockGitHubServer:
    """Mock GitHub MCP server for testing."""

    def __init__(self):
        self.server = FastMCP("mock-github-server")
        self.call_log = []

        # Register all the tools
        self.server.tool(self.create_issue)
        self.server.tool(self.get_file_contents)
        self.server.tool(self.list_issues)
        self.server.tool(self.create_pull_request)
        self.server.tool(self.update_issue)
        self.server.tool(self.search_repositories)
        self.server.tool(self.fork_repository)

    async def create_issue(self, owner: str, repo: str, title: str, body: str = None) -> dict:
        """Create a new issue in a GitHub repository."""
        self.call_log.append({"method": "create_issue", "owner": owner, "repo": repo, "title": title})
        return {
            "issue_id": 123,
            "owner": owner,
            "repo": repo,
            "title": title,
            "body": body,
            "url": f"https://github.com/{owner}/{repo}/issues/123"
        }

    async def get_file_contents(self, owner: str, repo: str, path: str, branch: str = None) -> dict:
        """Get contents of a file from a GitHub repository."""
        self.call_log.append({"method": "get_file_contents", "owner": owner, "repo": repo, "path": path})
        return {
            "path": path,
            "content": f"Mock content of {path}",
            "sha": "abc123",
            "owner": owner,
            "repo": repo
        }

    async def list_issues(self, owner: str, repo: str, state: str = "open") -> dict:
        """List issues in a GitHub repository."""
        self.call_log.append({"method": "list_issues", "owner": owner, "repo": repo, "state": state})
        return {
            "issues": [
                {"id": 1, "title": "Issue 1", "state": state},
                {"id": 2, "title": "Issue 2", "state": state}
            ],
            "owner": owner,
            "repo": repo
        }

    async def create_pull_request(self, owner: str, repo: str, title: str, head: str, base: str, body: str = None) -> dict:
        """Create a pull request."""
        self.call_log.append({"method": "create_pull_request", "owner": owner, "repo": repo, "title": title})
        return {
            "pr_id": 456,
            "owner": owner,
            "repo": repo,
            "title": title,
            "head": head,
            "base": base,
            "url": f"https://github.com/{owner}/{repo}/pull/456"
        }

    async def update_issue(self, owner: str, repo: str, issue_number: int, title: str = None, body: str = None, state: str = None) -> dict:
        """Update an issue."""
        self.call_log.append({"method": "update_issue", "owner": owner, "repo": repo, "issue_number": issue_number})
        return {
            "issue_id": issue_number,
            "owner": owner,
            "repo": repo,
            "title": title,
            "state": state or "open",
            "updated": True
        }

    async def search_repositories(self, query: str, page: int = None, perPage: int = None) -> dict:
        """Search for repositories."""
        self.call_log.append({"method": "search_repositories", "query": query})
        return {
            "repositories": [
                {"name": "repo1", "owner": "owner1", "description": "Test repo 1"},
                {"name": "repo2", "owner": "owner2", "description": "Test repo 2"}
            ],
            "total_count": 2
        }

    async def fork_repository(self, owner: str, repo: str, organization: str = None) -> dict:
        """Fork a repository."""
        self.call_log.append({"method": "fork_repository", "owner": owner, "repo": repo})
        return {
            "forked_repo": f"{organization or 'current-user'}/{repo}",
            "original": f"{owner}/{repo}",
            "success": True
        }


class GitHubHandlers:
    """Handlers for GitHub operations with roots protection."""

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_issue(self, owner: str, repo: str, title: str, body: str = None):
        """Create an issue - requires root validation."""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_file_contents(self, owner: str, repo: str, path: str, branch: str = None):
        """Get file contents - requires root validation."""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def list_issues(self, owner: str, repo: str, state: str = "open"):
        """List issues - requires root validation."""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_pull_request(self, owner: str, repo: str, title: str, head: str, base: str, body: str = None):
        """Create a pull request - requires root validation."""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def update_issue(self, owner: str, repo: str, issue_number: int, title: str = None, body: str = None, state: str = None):
        """Update an issue - requires root validation."""
        pass

    async def search_repositories(self, query: str, page: int = None, perPage: int = None):
        """Search repositories - no root validation needed."""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def fork_repository(self, owner: str, repo: str, organization: str = None):
        """Fork a repository - requires root validation."""
        pass


@pytest.mark.asyncio
class TestGitHubNonFileRoots:
    """End-to-end tests for non-file roots with GitHub server."""

    async def test_github_org_level_roots(self):
        """Test organization-level root access control."""
        # Create mock GitHub server
        mock_server = MockGitHubServer()

        # Create proxy with RootsMiddleware
        handlers = GitHubHandlers()
        proxy = create_proxy(mock_server.server, server_name="github-proxy")
        proxy.add_middleware(RootsMiddleware(handlers=handlers))

        # Configure client with org-level roots
        async with Client(proxy, roots=["https://github.com/allowed-org/"]) as client:
            # Test allowed org access
            result = await client.call_tool(
                "create_issue",
                {
                    "owner": "allowed-org",
                    "repo": "repo1",
                    "title": "Test Issue",
                    "body": "This is a test"
                }
            )
            assert result.data["owner"] == "allowed-org"
            assert result.data["repo"] == "repo1"

            # Test different repo in same org - should work
            result = await client.call_tool(
                "list_issues",
                {
                    "owner": "allowed-org",
                    "repo": "repo2",
                    "state": "open"
                }
            )
            assert result.data["owner"] == "allowed-org"
            assert result.data["repo"] == "repo2"

            # Test denied org access
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "denied-org",
                        "repo": "repo1",
                        "title": "Should fail"
                    }
                )
            assert "Access denied" in str(exc_info.value)

            # Test unprotected method still works
            result = await client.call_tool(
                "search_repositories",
                {"query": "test"}
            )
            assert "repositories" in result.data

    async def test_github_specific_repo_roots(self):
        """Test specific repository-level root access control."""
        mock_server = MockGitHubServer()

        handlers = GitHubHandlers()
        proxy = create_proxy(mock_server.server, server_name="github-proxy")
        proxy.add_middleware(RootsMiddleware(handlers=handlers))

        # Configure client with specific repo roots
        roots = [
            "https://github.com/org1/specific-repo",
            "https://github.com/org2/another-repo"
        ]

        async with Client(proxy, roots=roots) as client:
            # Test allowed specific repo
            result = await client.call_tool(
                "get_file_contents",
                {
                    "owner": "org1",
                    "repo": "specific-repo",
                    "path": "README.md"
                }
            )
            assert result.data["owner"] == "org1"
            assert result.data["repo"] == "specific-repo"

            # Test another allowed repo
            result = await client.call_tool(
                "create_pull_request",
                {
                    "owner": "org2",
                    "repo": "another-repo",
                    "title": "Test PR",
                    "head": "feature",
                    "base": "main"
                }
            )
            assert result.data["owner"] == "org2"
            assert result.data["repo"] == "another-repo"

            # Test denied - different repo in same org
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "org1",
                        "repo": "different-repo",
                        "title": "Should fail"
                    }
                )
            assert "Access denied" in str(exc_info.value)

    async def test_github_dynamic_roots_changes(self):
        """Test dynamic root changes via notifications."""
        mock_server = MockGitHubServer()

        handlers = GitHubHandlers()
        proxy = create_proxy(mock_server.server, server_name="github-proxy")
        proxy.add_middleware(RootsMiddleware(handlers=handlers))

        # Start with one set of roots
        current_roots = ["https://github.com/initial-org/"]

        async def dynamic_roots_handler(context):
            """Return current roots dynamically."""
            return current_roots

        async with Client(proxy, roots=dynamic_roots_handler) as client:
            # Test initial org works
            result = await client.call_tool(
                "create_issue",
                {
                    "owner": "initial-org",
                    "repo": "repo1",
                    "title": "Initial test"
                }
            )
            assert result.data["owner"] == "initial-org"

            # Test other org fails
            with pytest.raises(Exception):
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "new-org",
                        "repo": "repo1",
                        "title": "Should fail"
                    }
                )

            # Change roots to new org
            current_roots.clear()
            current_roots.append("https://github.com/new-org/")
            await client.send_roots_list_changed()

            # Now initial org should fail
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "initial-org",
                        "repo": "repo1",
                        "title": "Should now fail"
                    }
                )
            assert "Access denied" in str(exc_info.value)

            # And new org should work
            result = await client.call_tool(
                "create_issue",
                {
                    "owner": "new-org",
                    "repo": "repo1",
                    "title": "Should now work"
                }
            )
            assert result.data["owner"] == "new-org"

    async def test_github_multiple_mixed_roots(self):
        """Test multiple roots with different granularities."""
        mock_server = MockGitHubServer()

        handlers = GitHubHandlers()
        proxy = create_proxy(mock_server.server, server_name="github-proxy")
        proxy.add_middleware(RootsMiddleware(handlers=handlers))

        # Mix of org-level and repo-specific roots
        roots = [
            "https://github.com/public-org/",  # All repos in public-org
            "https://github.com/private-org/allowed-repo",  # Only specific repo in private-org
            "https://github.com/partner-org/project1",  # Specific project
            "https://github.com/partner-org/project2",  # Another specific project
        ]

        async with Client(proxy, roots=roots) as client:
            # Test org-level access
            result = await client.call_tool(
                "create_issue",
                {
                    "owner": "public-org",
                    "repo": "any-repo",
                    "title": "Org level access"
                }
            )
            assert result.data["owner"] == "public-org"

            # Test specific repo in private org
            result = await client.call_tool(
                "update_issue",
                {
                    "owner": "private-org",
                    "repo": "allowed-repo",
                    "issue_number": 42,
                    "title": "Updated"
                }
            )
            assert result.data["owner"] == "private-org"
            assert result.data["repo"] == "allowed-repo"

            # Test denied repo in private org
            with pytest.raises(Exception):
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "private-org",
                        "repo": "other-repo",
                        "title": "Should fail"
                    }
                )

            # Test allowed partner projects
            result = await client.call_tool(
                "fork_repository",
                {
                    "owner": "partner-org",
                    "repo": "project1"
                }
            )
            assert result.data["original"] == "partner-org/project1"

            result = await client.call_tool(
                "list_issues",
                {
                    "owner": "partner-org",
                    "repo": "project2"
                }
            )
            assert result.data["owner"] == "partner-org"

            # Test denied partner project
            with pytest.raises(Exception):
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "partner-org",
                        "repo": "project3",
                        "title": "Should fail"
                    }
                )

    async def test_github_with_fast_agent(self):
        """Test GitHub server with fast-agent configuration."""
        # Create mock GitHub server
        mock_server = MockGitHubServer()

        # Create proxy with RootsMiddleware
        handlers = GitHubHandlers()
        proxy = create_proxy(mock_server.server, server_name="github-proxy")
        proxy.add_middleware(RootsMiddleware(handlers=handlers))

        # Create temporary config for fast-agent
        test_dir = Path("/tmp/github_test")
        test_dir.mkdir(exist_ok=True)

        # Create config file
        config_file = test_dir / "config.json"
        config_data = {
            "mcpServers": {
                "github-proxy": {
                    "transport": "direct",
                    "server": proxy
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        # Create instruction file
        instruction_file = test_dir / "instruction.txt"
        instruction_file.write_text(
            "You are a helpful assistant that can work with GitHub repositories. "
            "Always be concise in your responses."
        )

        # Configure fast-agent
        fast = FastAgent("GitHubTest", config_path=str(config_file))

        # Define agent with roots
        @fast.agent(
            name="github_agent",
            model="gpt-4o-mini",
            servers=["github-proxy"],
            instruction=instruction_file,
            roots=["https://github.com/test-org/"]
        )
        async def github_agent():
            pass

        # Run test conversation
        async with fast.run() as agent_app:
            # Test allowed operation
            await agent_app.send(
                "Create an issue in test-org/test-repo with title 'Bug Report' and body 'Found a bug'"
            )

            # Check that the tool was called successfully
            assert len(mock_server.call_log) > 0
            last_call = mock_server.call_log[-1]
            assert last_call["method"] == "create_issue"
            assert last_call["owner"] == "test-org"
            assert last_call["repo"] == "test-repo"

            # Clear log
            mock_server.call_log.clear()

            # Test denied operation
            await agent_app.send(
                "Create an issue in other-org/repo with title 'Should Fail'"
            )

            # Should have tried but failed due to roots
            # The agent should have gotten an error and responded accordingly
            # We can check the conversation history to verify this
            messages = agent_app._agent(None).message_history

            # Look for error message in the conversation
            error_found = False
            for msg in messages:
                if hasattr(msg, 'content') and msg.content:
                    if "Access denied" in str(msg.content) or "not in allowed roots" in str(msg.content):
                        error_found = True
                        break

            assert error_found, "Expected access denied error in conversation"

    async def test_github_no_roots_fail_closed(self):
        """Test that GitHub operations fail when no roots are configured."""
        mock_server = MockGitHubServer()

        handlers = GitHubHandlers()
        proxy = create_proxy(mock_server.server, server_name="github-proxy")
        proxy.add_middleware(RootsMiddleware(handlers=handlers))

        # Client with no roots
        async with Client(proxy) as client:
            # All protected operations should fail
            with pytest.raises(Exception) as exc_info:
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "any-org",
                        "repo": "any-repo",
                        "title": "Should fail"
                    }
                )
            assert "No roots configured" in str(exc_info.value)

            # Unprotected operations should still work
            result = await client.call_tool(
                "search_repositories",
                {"query": "test"}
            )
            assert "repositories" in result.data

    async def test_github_prefix_matching_edge_cases(self):
        """Test edge cases in prefix matching for GitHub URLs."""
        mock_server = MockGitHubServer()

        handlers = GitHubHandlers()
        proxy = create_proxy(mock_server.server, server_name="github-proxy")
        proxy.add_middleware(RootsMiddleware(handlers=handlers))

        # Test that prefix matching is exact
        roots = ["https://github.com/myorg/"]

        async with Client(proxy, roots=roots) as client:
            # Should work - exact prefix match
            result = await client.call_tool(
                "create_issue",
                {
                    "owner": "myorg",
                    "repo": "myrepo",
                    "title": "Test"
                }
            )
            assert result.data["owner"] == "myorg"

            # Should fail - "myorg-other" doesn't match "myorg/" prefix
            with pytest.raises(Exception):
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "myorg-other",
                        "repo": "repo",
                        "title": "Should fail"
                    }
                )

            # Should fail - "myorganization" doesn't match "myorg/" prefix
            with pytest.raises(Exception):
                await client.call_tool(
                    "create_issue",
                    {
                        "owner": "myorganization",
                        "repo": "repo",
                        "title": "Should fail"
                    }
                )