"""Reporting utilities for AppWorld test results."""

import json
from pathlib import Path

from appworld.common.path_store import path_store
from appworld.task import Task


def find_evaluation_report(task_id: str, experiment_name: str) -> Path | None:
    """Find the evaluation report for a given task_id and experiment_name."""
    exp_base = Path(path_store.experiment_outputs)
    report_path = exp_base / experiment_name / "tasks" / task_id / "evaluation" / "report.md"
    return report_path if report_path.exists() else None


def parse_evaluation_report(report_path: Path) -> dict:
    """Parse evaluation report to determine pass/fail status."""
    content = report_path.read_text()
    lines = content.split("\n")

    passed = 0
    failed = 0

    for line in lines:
        if line.startswith("Num Passed Tests"):
            passed = int(line.split(":")[-1].strip())
        elif line.startswith("Num Failed Tests"):
            failed = int(line.split(":")[-1].strip())

    return {
        "success": failed == 0,
        "passed": passed,
        "failed": failed,
        "report_content": content,
    }


def load_complete_json(output_dir: Path, task_id: str) -> dict | None:
    """Load the complete.json file for a task."""
    complete_path = output_dir / "raw" / f"{task_id}_complete.json"
    if not complete_path.exists():
        return None
    return json.loads(complete_path.read_text())


def format_tool_call(tool_call_data: dict) -> str:
    """Format a tool call for display."""
    func_name = tool_call_data.get("name", "unknown")
    args = tool_call_data.get("arguments", {})

    # Format arguments
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except:
            pass

    if isinstance(args, dict) and args:
        arg_strs = [f"{k}={repr(v)}" for k, v in args.items()]
        return f"{func_name}({', '.join(arg_strs)})"
    else:
        return f"{func_name}()"


def generate_failure_report(
    task_id: str,
    task: Task,
    eval_data: dict,
    complete_data: dict | None,
    output_path: Path,
) -> None:
    """Generate a detailed failure report markdown file."""

    report = []
    report.append(f"# {task_id}\n")
    report.append("## Task\n")
    report.append(f"> {task.instruction}\n")
    metadata = task.ground_truth.metadata
    report.append(
        f"**Difficulty:** {metadata.get('difficulty', '?')}/5 | **Apps:** {metadata.get('num_apps', '?')} | **APIs:** {metadata.get('num_apis', '?')} | **Expected API calls:** {metadata.get('num_api_calls', '?')}\n"
    )
    report.append("---\n")

    # Evaluation Results
    report.append("## Evaluation Results\n")
    if eval_data["success"]:
        report.append("**Status:** ✅ PASSED\n")
    else:
        report.append(
            f"**Status:** ❌ FAILED ({eval_data['failed']}/{eval_data['passed'] + eval_data['failed']} requirements failed)\n"
        )
    report.append("\n```\n")
    report.append(eval_data["report_content"])
    report.append("\n```\n")
    report.append("---\n")

    # Ground Truth Solution
    report.append("## Ground Truth Solution Code\n")
    report.append("\nAppWorld's reference solution:\n")
    report.append("\n```python\n")
    report.append(task.ground_truth.solution_code)
    report.append("\n```\n")
    report.append("---\n")

    # Agent Execution Trace
    if complete_data:
        report.append("## Agent Execution Trace\n")
        messages = complete_data.get("messages", [])
        turn_num = 0

        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant":
                turn_num += 1
                report.append(f"\n### Turn {turn_num}\n")

                # Text content (show first - what the assistant said)
                if msg.get("content"):
                    for content_block in msg["content"]:
                        if content_block.get("type") == "text":
                            text = content_block.get("text", "")
                            if text.strip():
                                report.append("\n**Assistant:**\n")
                                report.append(f"> {text}\n")

                # Tool calls (show after text - what tools were invoked)
                if msg.get("tool_calls"):
                    # Look ahead to the next message for tool results
                    next_msg = messages[i + 1] if i + 1 < len(messages) else None
                    tool_results = next_msg.get("tool_results", {}) if next_msg else {}

                    for tool_call_id, tool_call_data in msg["tool_calls"].items():
                        report.append("\n**Tool Call:**\n")
                        report.append("```python\n")
                        report.append(format_tool_call(tool_call_data))
                        report.append("\n```\n")

                        # Find corresponding result in the next message
                        tool_result = tool_results.get(tool_call_id)
                        if tool_result:
                            # Extract text from content blocks
                            content_blocks = tool_result.get("content", [])
                            result_text = ""
                            for block in content_blocks:
                                if block.get("type") == "text":
                                    result_text = block.get("text", "")
                                    break

                            if result_text:
                                report.append("\n**Result:**\n")
                                report.append("```json\n")
                                report.append(result_text)
                                report.append("\n```\n")
    else:
        report.append("## Agent Execution Trace\n")
        report.append("\n⚠️  No execution trace available (complete.json not found)\n")

    output_path.write_text("\n".join(report))
