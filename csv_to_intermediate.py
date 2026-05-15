#!/usr/bin/env python3
"""Read annotation CSVs and produce cases.yaml with per-case trigger configs and feedback messages."""

import csv
import re
import sys
from pathlib import Path

import yaml


ANNOTATIONS_CSV = Path("annotations/Trigger Annotation Template.xlsx - Trigger Annotations.csv")
MESSAGES_CSV = Path("annotations/Trigger Annotation Template.xlsx - Feedback Messages.csv")
OUTPUT_YAML = Path("cases.yaml")


def load_messages(path: Path) -> dict:
    """Load feedback messages keyed by (subset, tool_name).

    Returns dict mapping (subset, tool) -> {specific, vague, verbose, null}.
    """
    messages = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            subset = row["Subset"].strip()
            tool = row["Trigger Tool"].strip()
            key = (subset, tool)
            messages[key] = {
                "specific": row["Specific"].strip(),
                "vague": row["Vague"].strip(),
                "verbose": row["Verbose"].strip(),
                "null": row["Null"].strip(),
            }
    return messages


def load_annotations(path: Path) -> list[dict]:
    """Load trigger annotations. Cases with N/A tools are included with trigger: null."""
    cases = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tool_raw = row["Tool Called Incorrectly"].strip()
            case = {
                "case_id": row["Test Case ID"].strip(),
                "subset": row["Subset"].strip(),
                "pattern": row["Failure Pattern"].strip(),
            }
            if tool_raw and tool_raw != "N/A":
                tool_name = re.split(r"[\n,]", tool_raw)[0].strip()
                case["tool_name"] = tool_name
                case["trigger_type"] = row["trigger_type\n(for config)"].strip()
            cases.append(case)
    return cases


def build_cases(annotations: list[dict], messages: dict) -> list[dict]:
    missing = []
    cases = []
    for ann in annotations:
        tool_name = ann.get("tool_name")
        if tool_name is None:
            cases.append({
                "case_id": ann["case_id"],
                "subset": ann["subset"],
                "pattern": ann["pattern"],
                "trigger": None,
                "messages": None,
            })
            continue
        key = (ann["subset"], tool_name)
        msg = messages.get(key)
        if msg is None:
            missing.append(key)
            continue
        for variant in ("specific", "vague", "verbose", "null"):
            if not msg[variant]:
                missing.append((*key, variant))
        cases.append({
            "case_id": ann["case_id"],
            "subset": ann["subset"],
            "pattern": ann["pattern"],
            "trigger": {
                "tool_name": tool_name,
                "trigger_type": ann["trigger_type"],
                "occurrence": "first",
            },
            "messages": {
                "specific": msg["specific"],
                "vague": msg["vague"],
                "verbose": msg["verbose"],
                "null": msg["null"],
            },
        })
    if missing:
        raise ValueError(
            f"Missing feedback message data for the following (subset, tool) pairs:\n"
            + "\n".join(f"  {m}" for m in missing)
        )
    return cases


def main():
    annotations = load_annotations(ANNOTATIONS_CSV)
    messages = load_messages(MESSAGES_CSV)
    cases = build_cases(annotations, messages)
    with open(OUTPUT_YAML, "w") as f:
        yaml.dump(cases, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)
    print(f"Wrote {len(cases)} cases to {OUTPUT_YAML}")


if __name__ == "__main__":
    main()
