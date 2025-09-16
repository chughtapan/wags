"""Evaluation framework for benchmarks with fast-agent and MCP."""

from .core import MessageSerializer, StructuredEventLogger, TestConfig, run_test_async

__version__ = "0.1.0"

__all__ = [
    "MessageSerializer",
    "StructuredEventLogger",
    "TestConfig",
    "run_test_async",
]
