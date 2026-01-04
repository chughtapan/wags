"""
data.py

Dataset loading utilities for GEPA on BFCL tests
"""

from __future__ import annotations
from typing import List, Any
from tests.benchmarks.bfcl import loader as bfcl_loader
from .agent import BFCLExample


def stringify_question(question: Any) -> str:
    
    if isinstance(question, list) and question:
        first = question[0]

        if isinstance(first, str):
            return first

        if isinstance(first, dict):
            return str(first.get("content", ""))

        if isinstance(first, list) and first:
            msg0 = first[0]
            if isinstance(msg0, dict):
                return str(msg0.get("content", ""))

    if isinstance(question, dict):
        return str(question.get("content", ""))

    if isinstance(question, str):
        return question

    return ""


def load_test_cases(subset: str, limit: int | None = None) -> List[BFCLExample]:
    """
    Load BFCL test cases from a given subset and return as BFCLExample objects
    """
    test_ids = bfcl_loader.find_tests_in_category(subset, limit=limit)
    examples: List[BFCLExample] = []
    for test_id in test_ids[:limit]:
        entry = bfcl_loader.load_test_entry(test_id)
        question = stringify_question(entry.get("question", ""))
        ex = BFCLExample(test_id=test_id, question=question)
        examples.append(ex.with_inputs("test_id", "question"))

    return examples
