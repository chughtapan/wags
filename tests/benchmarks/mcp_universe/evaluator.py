"""Evaluation logic for MCP-Universe test results."""

from pathlib import Path
from typing import Any

from mcpuniverse.common.context import Context
from mcpuniverse.evaluator.evaluator import EvaluationResult, Evaluator

from .loader import load_task


async def run_evaluation(
    task_id: str,
    context: Context,
) -> dict[str, Any]:
    """
    Run evaluation for a repository management task.

    Args:
        task_id: Test case identifier
        context: MCP-Universe context with environment variables

    Returns:
        Dictionary with evaluation results
    """
    # Load task data
    task = load_task(task_id)

    # Set MCP server config path for the evaluator
    # This tells MCPManager where to find the GitHub MCP server configuration
    mcp_config_path = Path(__file__).parent / "mcp_server_config.json"
    context.env["MCP_SERVER_CONFIG"] = str(mcp_config_path)

    # Run all evaluators
    evaluation_results: list[EvaluationResult] = []

    for evaluator_config in task.get("evaluators", []):
        evaluator = Evaluator(evaluator_config, context=context)
        result = await evaluator.evaluate({})
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
