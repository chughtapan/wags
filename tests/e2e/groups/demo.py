#!/usr/bin/env python
"""Interactive demo of GroupsMiddleware with FastAgent.

Usage:
    python tests/e2e/groups/demo.py
    python tests/e2e/groups/demo.py --model gpt-5
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from fast_agent import FastAgent

script_dir = os.path.dirname(__file__)
os.chdir(script_dir)

fast = FastAgent(
    "Groups Demo",
    config_path=os.path.join(script_dir, "fastagent.config.yaml"),
)


@fast.agent(
    name="demo",
    servers=["mock-github-groups"],
    instruction="You are an autonomous assistant. Complete tasks without asking for confirmation.",
)
async def demo() -> None:
    async with fast.run() as agent:
        await agent()


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo())
