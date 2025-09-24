"""Integration tests for GitHub MCP server with middleware.

Tests the GitHub server with various middleware configurations including
RootsMiddleware for access control and potential future middleware.
"""

import pytest

from tests.utils.fastagent_helpers import get_result_text, get_tool_calls, get_tool_results


class TestGitHubRootsMiddleware:
    """Test GitHub server with RootsMiddleware access control."""

    @pytest.mark.asyncio
    async def test_allowed_repository_access(self, fast_agent):
        """Test that access to configured roots (anthropics/courses) is allowed."""
        fast = fast_agent

        @fast.agent(
            name="test",
            model="gpt-4o-mini",
            servers=["github"],
            instruction="You are a concise GitHub assistant. Always use the available GitHub tools.",
        )
        async def test_function():
            async with fast.run() as agent:
                # Request access to anthropics/courses (in allowed roots)
                await agent.send(
                    "List open issues in the GitHub repository owned by 'anthropics' named 'courses'"
                )

                # Extract tool calls and results from message history
                messages = agent._agent(None).message_history
                tool_calls = get_tool_calls(messages)
                tool_results = get_tool_results(messages)

                # Verify tool was called
                assert len(tool_calls) > 0

                # Find the GitHub list_issues call
                github_call = None
                for tool_id, request in tool_calls:
                    if request.params.name == "github-list_issues":
                        github_call = (tool_id, request)
                        break

                assert github_call is not None

                # Verify correct repository parameters
                tool_id, request = github_call
                assert request.params.arguments.get("owner") == "anthropics"
                assert request.params.arguments.get("repo") == "courses"

                # Verify successful response (not blocked by middleware)
                assert tool_id in tool_results
                result = tool_results[tool_id]
                assert not result.isError

        await test_function()

    @pytest.mark.asyncio
    async def test_denied_repository_access(self, fast_agent):
        """Test that access to non-configured roots (github/docs) is denied."""
        fast = fast_agent

        @fast.agent(
            name="test",
            model="gpt-4o-mini",
            servers=["github"],
            instruction="You are a concise GitHub assistant. Always use the available GitHub tools.",
        )
        async def test_function():
            async with fast.run() as agent:
                # Request access to github/docs (NOT in allowed roots)
                await agent.send(
                    "List open issues in the GitHub repository owned by 'github' named 'docs'"
                )

                # Extract tool calls and results from message history
                messages = agent._agent(None).message_history
                tool_calls = get_tool_calls(messages)
                tool_results = get_tool_results(messages)

                # Verify tool was called
                assert len(tool_calls) > 0

                # Find the GitHub list_issues call
                github_call = None
                for tool_id, request in tool_calls:
                    if request.params.name == "github-list_issues":
                        github_call = (tool_id, request)
                        break

                assert github_call is not None

                # Verify correct repository parameters
                tool_id, request = github_call
                assert request.params.arguments.get("owner") == "github"
                assert request.params.arguments.get("repo") == "docs"

                # Verify middleware denied access (error response)
                assert tool_id in tool_results
                result = tool_results[tool_id]
                assert result.isError

                # Verify error message indicates access denial
                error_text = get_result_text(result)
                assert "not in allowed roots" in error_text

        await test_function()

    @pytest.mark.asyncio
    async def test_organization_wildcard_access(self, fast_agent):
        """Test that wildcard organization access (modelcontextprotocol/*) works."""
        fast = fast_agent

        @fast.agent(
            name="test",
            model="gpt-4o-mini",
            servers=["github"],
            instruction="You are a concise GitHub assistant. Always use the available GitHub tools.",
        )
        async def test_function():
            async with fast.run() as agent:
                # Request access to any repo in modelcontextprotocol org
                await agent.send(
                    "Get information about the repository owned by 'modelcontextprotocol' named 'servers'"
                )

                # Extract tool calls and results
                messages = agent._agent(None).message_history
                tool_calls = get_tool_calls(messages)
                tool_results = get_tool_results(messages)

                # Verify a GitHub tool was called
                assert len(tool_calls) > 0

                # Find any successful GitHub API call for this org
                success_found = False
                for tool_id, request in tool_calls:
                    if "github-" in request.params.name:
                        args = request.params.arguments
                        # Check if this call was for the modelcontextprotocol org
                        if args.get("owner") == "modelcontextprotocol":
                            # Check if the call succeeded
                            if tool_id in tool_results:
                                result = tool_results[tool_id]
                                if not result.isError:
                                    success_found = True
                                    break

                assert success_found, "Should have successful access to modelcontextprotocol org"

        await test_function()


# Future test classes can be added here for other middleware:
# class TestGitHubElicitationMiddleware:
#     """Test GitHub server with ElicitationMiddleware for parameter collection."""
#     pass