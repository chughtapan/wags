#!/usr/bin/env python3
"""Experiment runner for BFCL external-feedback conditions.

Runs the BFCL evaluation suite for a single (subset, condition) cell.
Resolves the right config file, sets all required environment variables,
and delegates to pytest with appropriate flags.

Usage
-----
    # Run subset A with specific-label feedback
    python scripts/run_experiment.py --subset A --condition specific

    # Override the test-case list (comma-separated IDs)
    python scripts/run_experiment.py --subset E --condition vague \\
        --test-ids multi_turn_base_62,multi_turn_base_70

    # Dry-run: print the pytest command without executing it
    python scripts/run_experiment.py --subset D --condition specific --dry-run

    # Extra pytest flags are forwarded verbatim after --
    python scripts/run_experiment.py --subset A --condition specific -- -x -v

Output
------
Results are written to ``results/<subset>/<condition>/``:

    results/A/specific/raw/<test_id>_complete.json
    results/A/specific/raw/<test_id>_structured.jsonl
    results/A/specific/raw/<test_id>_evaluation.json
    results/A/specific/raw/external_feedback.jsonl   ← structured trigger log
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths relative to repo root
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
BFCL_DIR = REPO_ROOT / "tests" / "benchmarks" / "bfcl"
CONFIGS_DIR = BFCL_DIR / "configs"
RESULTS_DIR = REPO_ROOT / "outputs" / "feedback"

VALID_SUBSETS = {"A", "B", "C", "D", "E", "F", "G"}
VALID_CONDITIONS = {"specific", "vague", "verbose", "null"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_config(subset: str, condition: str) -> Path:
    """Return the path to the JSON config file for this cell.

    Raises FileNotFoundError with a helpful message if not found.
    """
    candidate = CONFIGS_DIR / f"{subset}_{condition}.json"
    if not candidate.exists():
        available = sorted(CONFIGS_DIR.glob("*.json"))
        hint = "\n  ".join(str(p.name) for p in available) or "(none)"
        raise FileNotFoundError(
            f"Config file not found: {candidate}\n"
            f"Available configs in {CONFIGS_DIR}:\n  {hint}"
        )
    return candidate


def load_test_ids_from_config(config_path: Path) -> list[str]:
    """Read the test_ids list from the config file."""
    with open(config_path) as fh:
        config = json.load(fh)
    return config.get("test_ids", [])


def build_pytest_filter(test_ids: list[str]) -> str:
    """Build a pytest -k expression that matches exactly the given test IDs.

    pytest parametrises each test as ``test_bfcl[<test_id>]`` so we match on
    the bracketed ID substring.
    """
    if not test_ids:
        return ""
    # Wrap each ID in brackets to match the exact parametrized name (e.g. [multi_turn_base_0])
    # and avoid substring matches (e.g. multi_turn_base_0 matching multi_turn_base_100).
    return " or ".join(f"[{tid}]" for tid in test_ids)


def build_env(
    config_path: Path,
    output_dir: Path,
    model: str,
    temperature: float,
) -> dict[str, str]:
    """Construct the environment for the pytest subprocess."""
    env = os.environ.copy()
    env.update(
        {
            # Master switch — tells mcp_server.py to activate WAGS proxy mode.
            "BFCL_EXTERNAL_FEEDBACK_ENABLED": "1",
            # Points the middleware to the rules file for this cell.
            "BFCL_EXTERNAL_FEEDBACK_CONFIG": str(config_path.resolve()),
            # Structured JSONL log — one record per evaluated tool call.
            "BFCL_EXTERNAL_FEEDBACK_LOG_FILE": str(
                (output_dir / "raw" / "external_feedback.jsonl").resolve()
            ),
            # Forwarded to FastAgent / fastagent.config.yaml interpolation.
            "DEFAULT_MODEL": model,
            "TEMPERATURE": str(temperature),
        }
    )
    return env


def build_pytest_command(
    output_dir: Path,
    model: str,
    temperature: float,
    k_filter: str,
    extra_args: list[str],
) -> list[str]:
    """Assemble the full pytest invocation."""
    cmd = [
        sys.executable, "-m", "pytest",
        str(BFCL_DIR / "test_bfcl.py"),
        # Enable the external-feedback flag so test_bfcl.py passes it through.
        "--external-feedback",
        "--output-dir", str(output_dir.resolve()),
        "--model", model,
        "--temperature", str(temperature),
    ]
    if k_filter:
        cmd += ["-k", k_filter]
    cmd += extra_args
    return cmd


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run BFCL eval for one (subset × condition) experimental cell.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--subset",
        required=True,
        choices=sorted(VALID_SUBSETS),
        help="Experimental subset ID (A–G).",
    )
    parser.add_argument(
        "--condition",
        required=True,
        choices=sorted(VALID_CONDITIONS),
        help="Feedback condition label.",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help=(
            f"Directory containing config files "
            f"(default: {CONFIGS_DIR})."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Root output directory.  Results go to "
            "<output-dir>/<subset>/<condition>/  "
            f"(default: {RESULTS_DIR})."
        ),
    )
    parser.add_argument(
        "--model",
        default="gpt-5",
        help="LLM model name.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.00,
        help="Sampling temperature (default: 0.00).",
    )
    parser.add_argument(
        "--test-ids",
        default=None,
        help=(
            "Comma-separated list of BFCL test IDs to run.  "
            "Overrides the test_ids field in the config file."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved config, env vars, and pytest command without running.",
    )
    return parser.parse_known_args(argv)


def main(argv: list[str] | None = None) -> int:
    args, extra_pytest_args = parse_args(argv)

    # Strip a leading "--" separator used to pass extra pytest args.
    if extra_pytest_args and extra_pytest_args[0] == "--":
        extra_pytest_args = extra_pytest_args[1:]

    # ---- Resolve config ----
    configs_dir = Path(args.config_dir) if args.config_dir else CONFIGS_DIR
    config_path = configs_dir / f"{args.subset}_{args.condition}.json"
    if not config_path.exists():
        available = sorted(configs_dir.glob("*.json"))
        hint = "\n  ".join(p.name for p in available) or "(none found)"
        print(
            f"ERROR: Config file not found: {config_path}\n"
            f"Available configs in {configs_dir}:\n  {hint}",
            file=sys.stderr,
        )
        return 1

    # ---- Resolve test IDs ----
    if args.test_ids:
        test_ids = [t.strip() for t in args.test_ids.split(",") if t.strip()]
    else:
        test_ids = load_test_ids_from_config(config_path)

    if not test_ids:
        print(
            "WARNING: No test IDs specified and none found in config file.  "
            "pytest will run ALL multi-turn BFCL tests.",
            file=sys.stderr,
        )

    # ---- Output directory ----
    results_root = Path(args.output_dir) if args.output_dir else RESULTS_DIR
    output_dir = results_root / args.subset / args.condition
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "raw").mkdir(parents=True, exist_ok=True)

    # ---- Build command and environment ----
    k_filter = build_pytest_filter(test_ids)
    env = build_env(config_path, output_dir, args.model, args.temperature)
    cmd = build_pytest_command(
        output_dir, args.model, args.temperature, k_filter, extra_pytest_args
    )

    # ---- Dry run: just print ----
    if args.dry_run:
        print("=== Config file ===")
        print(f"  {config_path}")
        print(f"\n=== Test IDs ({len(test_ids)}) ===")
        for tid in test_ids:
            print(f"  {tid}")
        print("\n=== Output directory ===")
        print(f"  {output_dir}")
        print("\n=== Environment overrides ===")
        feedback_keys = [k for k in env if k.startswith("BFCL_") or k in {"DEFAULT_MODEL", "TEMPERATURE"}]
        for k in sorted(feedback_keys):
            print(f"  {k}={env[k]}")
        print("\n=== pytest command ===")
        print("  " + " ".join(cmd))
        return 0

    # ---- Run ----
    print(
        f"[run_experiment] subset={args.subset} condition={args.condition} "
        f"model={args.model} tests={len(test_ids) or 'all'}",
        flush=True,
    )
    print(f"[run_experiment] Output: {output_dir}", flush=True)
    print(f"[run_experiment] Config: {config_path}", flush=True)

    result = subprocess.run(cmd, env=env, cwd=str(REPO_ROOT))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
