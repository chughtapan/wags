"""Integration tests for GitHub MCP server with middleware.

Tests the GitHub server proxied through wags middleware.
"""

import pytest
from fast_agent import FastAgent

from tests.utils.fastagent_helpers import get_tool_calls, get_tool_results


class TestGitHubServer:
    """Test GitHub server through the wags proxy."""

    @pytest.mark.asyncio
    async def test_repository_access(self, fast_agent: FastAgent, model: str) -> None:
        """Test that the agent can list issues in a repository."""
        fast = fast_agent

        @fast.agent(
            name="test",
            model=model,
            servers=["github"],
            instruction="You are a concise GitHub assistant. Always use the available GitHub tools.",
        )
        async def test_function() -> None:
            async with fast.run() as agent:
                await agent.send("List open issues in the GitHub repository owned by 'anthropics' named 'courses'")

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
                assert request.params.arguments and request.params.arguments.get("owner") == "anthropics"
                assert request.params.arguments and request.params.arguments.get("repo") == "courses"

                # Verify successful response (not blocked by middleware)
                assert tool_id in tool_results
                result = tool_results[tool_id]
                assert not result.is_error

        await test_function()


# Future test classes can be added here for other middleware:
# class TestGitHubElicitationMiddleware:
#     """Test GitHub server with ElicitationMiddleware for parameter collection."""
#     pass
