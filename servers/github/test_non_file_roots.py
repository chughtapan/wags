#!/usr/bin/env python
"""Test script demonstrating non-file roots with GitHub MCP server.

This shows how RootsMiddleware controls access to GitHub repos using URLs.
"""

import asyncio
import os
from pathlib import Path

from fast_agent import FastAgent


async def test_github_roots():
    """Test GitHub non-file roots feature."""

    # Check for GitHub token
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        print("⚠️  Please set GITHUB_PERSONAL_ACCESS_TOKEN environment variable")
        print("   Create token at: https://github.com/settings/tokens")
        return

    # Use the config with roots configured
    config_path = Path(__file__).parent / "fastagent.config.yaml"

    # Create FastAgent
    fast = FastAgent("GitHubRootsTest", config_path=str(config_path))

    print("\n" + "="*60)
    print("GitHub Non-File Roots Test")
    print("="*60)
    print("\nThis test demonstrates how RootsMiddleware controls")
    print("access to GitHub repositories using URL-based roots.\n")
    print("Configured roots:")
    print("  - https://github.com/anthropics/courses (specific repo)")
    print("  - https://github.com/modelcontextprotocol/* (entire org)")
    print()

    @fast.agent(
        name="test_agent",
        model="gpt-4o-mini",
        servers=["github"],
        instruction="You are a concise GitHub assistant. Always use the available GitHub tools to fulfill requests."
    )
    async def test_agent():
        pass

    async with fast.run() as agent_app:
        # Test 1: Allowed specific repo
        print("Test 1: Accessing allowed repository (anthropics/courses)")
        print("-" * 40)
        response = await agent_app.send("List any open issues in anthropics/courses")
        print(f"Response: {response}")
        await asyncio.sleep(1)

        # Test 2: Allowed org (any repo in modelcontextprotocol)
        print("\nTest 2: Accessing allowed org (modelcontextprotocol/*)")
        print("-" * 40)
        response = await agent_app.send("Check for issues in modelcontextprotocol/servers")
        print(f"Response: {response}")
        await asyncio.sleep(1)

        # Test 3: Denied repo (not in roots)
        print("\nTest 3: Attempting denied repository (github/docs)")
        print("-" * 40)
        response = await agent_app.send("List issues in github/docs repository")
        print(f"Response: {response}")
        await asyncio.sleep(1)

        # Analyze results
        messages = agent_app._agent(None).message_history

        print("\n" + "="*60)
        print("Results:")
        print("="*60)

        # Check for access control
        access_denied = False
        tool_calls = 0
        for msg in messages:
            # Check for tool calls
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_calls += len(msg.tool_calls)

            # Check for access denials
            if hasattr(msg, 'content') and msg.content:
                content = str(msg.content)
                if "Access denied" in content or "not in allowed roots" in content:
                    access_denied = True
                    print("✓ Access control working - denied unauthorized access")

        print(f"\nTotal tool calls made: {tool_calls}")

        if not access_denied:
            print("⚠️  No explicit access denial found in responses")
            print("    (The agent may have handled the denial gracefully)")

        print("\nExpected behavior:")
        print("  ✓ Allowed access to anthropics/courses")
        print("  ✓ Allowed access to modelcontextprotocol/* repos")
        print("  ✗ Denied access to github/docs (not in roots)")

    print("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(test_github_roots())