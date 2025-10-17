"""Evaluation logic for MCP-Universe test results."""

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add MCP-Universe to Python path
mcp_universe_path = Path(__file__).parent / "data"
if str(mcp_universe_path) not in sys.path:
    sys.path.insert(0, str(mcp_universe_path))

from mcpuniverse.common.context import Context
from mcpuniverse.evaluator.evaluator import Evaluator, EvaluationResult

from .loader import load_task


async def run_evaluation(
    task_id: str,
    context: Context | None = None,
) -> dict[str, Any]:
    """
    Run evaluation for a repository management task.

    Args:
        task_id: Test case identifier
        context: Optional MCP-Universe context with environment variables

    Returns:
        Dictionary with evaluation results
    """
    # Load task data
    task = load_task(task_id)

    # Create context if not provided
    if context is None:
        context = Context()

    # Set MCP server config path for the evaluator
    # This tells MCPManager where to find the GitHub MCP server configuration
    mcp_config_path = Path(__file__).parent / "mcp_server_config.json"
    context.env["MCP_SERVER_CONFIG"] = str(mcp_config_path)

    # Run all evaluators
    evaluation_results: list[EvaluationResult] = []

    for evaluator_config in task.get("evaluators", []):
        try:
            evaluator = Evaluator(evaluator_config, context=context)
            result = await evaluator.evaluate({})
            evaluation_results.append(result)
        except Exception as e:
            # Create a failed evaluation result
            from mcpuniverse.evaluator.evaluator import EvaluatorConfig

            config = EvaluatorConfig.model_validate(evaluator_config)
            result = EvaluationResult(
                config=config,
                response="",
                passed=False,
                error=str(e),
                reason=f"Evaluation failed: {str(e)}",
            )
            evaluation_results.append(result)

    # Calculate overall pass/fail
    all_passed = all(result.passed for result in evaluation_results)

    return {
        "task_id": task_id,
        "passed": all_passed,
        "evaluation_results": [
            {
                "func": result.config.func,
                "op": result.config.op,
                "passed": result.passed,
                "reason": result.reason,
                "error": result.error,
            }
            for result in evaluation_results
        ],
        "task_data": task,
    }
