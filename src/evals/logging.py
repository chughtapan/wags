"""File I/O operations."""

import json
from pathlib import Path
from typing import Any


def save_test_data(path: Path, data: dict[str, Any]) -> None:
    """Save test data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def save_conversation(history: list[Any], path: Path) -> None:
    """Save conversation history."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Format history for output
    formatted = []
    for msg in history:
        msg_data = {"role": msg.role, "content": []}
        for content in msg.content:
            content_data = {"type": getattr(content, "type", "unknown")}

            # Add available attributes
            for attr in ["text", "name", "input", "tool_use_id"]:
                if hasattr(content, attr):
                    content_data[attr] = getattr(content, attr)

            msg_data["content"].append(content_data)
        formatted.append(msg_data)

    path.write_text(json.dumps(formatted, indent=2))


def clear_log(path: Path) -> None:
    """Clear existing log file."""
    if path.exists():
        path.unlink()


def load_instruction(path: Path) -> str:
    """Load instruction text file."""
    return path.read_text()


def save_evaluation_results(path: Path, results: dict[str, Any]) -> None:
    """Save evaluation results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2))
