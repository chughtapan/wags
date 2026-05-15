#!/usr/bin/env python3
"""Read cases.yaml and generate per-cell JSON configs into tests/benchmarks/bfcl/configs/."""

import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml


CASES_YAML = Path("cases.yaml")
CONFIGS_DIR = Path("tests/benchmarks/bfcl/configs")
CONDITIONS = ("specific", "vague", "verbose", "null")

TRIGGER_TYPE_REQUIRED_FIELDS = {
    "tool_only": {"tool_name", "trigger_type", "occurrence"},
    "argument_present": {"tool_name", "trigger_type", "occurrence"},
    "argument_value": {"tool_name", "trigger_type", "occurrence"},
    "precondition_missing": {"tool_name", "trigger_type", "occurrence"},
}


def load_cases(path: Path) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def build_configs(cases: list[dict]) -> dict[tuple[str, str], dict]:
    subsets: dict[str, dict] = defaultdict(lambda: {"test_ids": [], "triggers": {}})

    for case in cases:
        subset = case["subset"]
        entry = subsets[subset]
        entry["test_ids"].append(case["case_id"])

        trigger = case.get("trigger")
        if trigger is None:
            continue

        tool_name = trigger["tool_name"]
        if tool_name not in entry["triggers"]:
            entry["triggers"][tool_name] = {
                "tool_name": tool_name,
                "trigger_type": trigger["trigger_type"],
                "occurrence": 1,
                "messages": case["messages"],
            }

    configs = {}
    for subset, entry in subsets.items():
        for condition in CONDITIONS:
            trigger_list = []
            for tool_name, trig in entry["triggers"].items():
                trigger_obj = {
                    "tool_name": trig["tool_name"],
                    "trigger_type": trig["trigger_type"],
                    "occurrence": trig["occurrence"],
                    "feedback_message": trig["messages"][condition],
                    "condition_label": condition,
                }
                trigger_list.append(trigger_obj)

            configs[(subset, condition)] = {
                "subset": subset,
                "condition": condition,
                "test_ids": sorted(entry["test_ids"]),
                "triggers": trigger_list,
            }

    return configs


def validate(configs: dict[tuple[str, str], dict]) -> list[str]:
    errors = []
    for (subset, condition), config in sorted(configs.items()):
        label = f"{subset}_{condition}"

        if not config["triggers"]:
            errors.append(f"{label}: triggers list is empty")
            continue

        for i, trig in enumerate(config["triggers"]):
            tt = trig.get("trigger_type")
            required = TRIGGER_TYPE_REQUIRED_FIELDS.get(tt)
            if required is None:
                errors.append(f"{label}: trigger[{i}] has unknown trigger_type {tt!r}")
                continue
            for field in sorted(required):
                val = trig.get(field)
                if val is None or (isinstance(val, str) and not val.strip()):
                    errors.append(f"{label}: trigger[{i}] missing required field '{field}'")

            msg = trig.get("feedback_message")
            if not msg or not msg.strip():
                errors.append(f"{label}: trigger[{i}] ({trig.get('tool_name')}) has empty feedback_message")

    return errors


def write_configs(configs: dict[tuple[str, str], dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for (subset, condition), config in sorted(configs.items()):
        path = output_dir / f"{subset}_{condition}.json"
        with open(path, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")


def main():
    cases = load_cases(CASES_YAML)
    configs = build_configs(cases)

    errors = validate(configs)
    if errors:
        print(f"VALIDATION FAILED — {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)

    write_configs(configs, CONFIGS_DIR)

    print(f"Validation passed — {len(configs)} configs, 0 errors")
    subsets = sorted(set(s for s, _ in configs))
    for subset in subsets:
        test_ids = configs[(subset, "specific")]["test_ids"]
        n_triggers = len(configs[(subset, "specific")]["triggers"])
        print(f"  {subset}: {len(test_ids)} test_ids, {n_triggers} trigger(s), {len(CONDITIONS)} conditions")
    print(f"\nWrote {len(configs)} files to {CONFIGS_DIR}/")


if __name__ == "__main__":
    main()
