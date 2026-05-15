"""Middleware that injects one-time external feedback for target tool calls.

Supports two modes:

**Config-file mode** (new)
    Set ``BFCL_EXTERNAL_FEEDBACK_CONFIG`` to a JSON file path.  The file
    contains a list of trigger rules; each rule fires independently with its
    own occurrence counter.  Every evaluated call — triggered or not — is
    appended as a JSON record to ``BFCL_EXTERNAL_FEEDBACK_LOG_FILE`` so that
    full agent trajectories can be reconstructed offline.

**Legacy env-var mode** (backward-compatible)
    If ``BFCL_EXTERNAL_FEEDBACK_CONFIG`` is not set the middleware falls back
    to the original single-tool behaviour driven by:
    ``BFCL_EXTERNAL_FEEDBACK_TOOL``, ``BFCL_EXTERNAL_FEEDBACK_MESSAGE``,
    ``BFCL_EXTERNAL_FEEDBACK_N``.

In both modes ``BFCL_EXTERNAL_FEEDBACK_ENABLED`` must be truthy for the
middleware to be active (the guard lives in ``mcp_server.py``; the class
itself does not re-check the flag).

Config file schema
------------------
See ``tests/benchmarks/bfcl/configs/`` for examples.  Top-level fields::

    subset        – "A" … "G"
    condition     – "specific" | "vague" | "verbose" | "null"
    description   – optional human note (ignored at runtime)
    test_ids      – list of BFCL test IDs this config applies to
    triggers      – list of trigger-rule objects (see TriggerRule)

Each trigger-rule object::

    tool_name           – (str, required) target tool, name-normalised on match
    trigger_type        – "tool_only" | "argument_present"
                          | "argument_value" | "precondition_missing"
    argument_conditions – (object, optional) shape varies by trigger_type
    occurrence          – (int) which matching call fires the trigger (1 = first)
    feedback_message    – (str) injected warning; empty string → bare rejection
    condition_label     – "specific" | "vague" | "verbose" | "null"

argument_conditions shapes
--------------------------
tool_only
    omit entirely

argument_present
    {"forbidden_args": ["param1", "param2"]}
    Fires when *any* listed key appears in the agent's arguments.

argument_value
    {"checks": [{"key": "speed", "op": "gt", "value": 120}], "match": "any"}
    Supported ops: eq, neq, gt, gte, lt, lte, in, not_in, contains.
    "match" is "any" (default) or "all".

precondition_missing
    {"required_prior_calls": ["startEngine"]}
    Fires when *any* listed tool has not yet been called in this session.
    Only tool calls that pass through (are not blocked) count as "called".
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams


# ---------------------------------------------------------------------------
# Internal data model
# ---------------------------------------------------------------------------

@dataclass
class TriggerRule:
    """A single trigger rule parsed from a config file or constructed directly."""

    tool_name: str
    tool_name_normalized: str
    trigger_type: str  # tool_only | argument_present | argument_value | precondition_missing
    argument_conditions: dict[str, Any] | None
    occurrence: int
    feedback_message: str
    condition_label: str

    # Runtime counters — mutated during execution, not sourced from config.
    match_count: int = field(default=0, init=False)
    fired: bool = field(default=False, init=False)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class ExternalFeedbackMiddleware(Middleware):
    """Config-driven (or legacy env-var) external-feedback injection middleware.

    Parameters
    ----------
    config:
        Pre-parsed config dict (mutually exclusive with *config_path*).
    config_path:
        Path to a JSON config file.  Loaded on ``__init__``.
    target_tool_name:
        Legacy mode: the single tool to watch.
    warning_message:
        Legacy mode: message to inject.
    trigger_on_nth_call:
        Legacy mode: which occurrence to fire on (default 1).
    """

    def __init__(
        self,
        *,
        # Config-file mode
        config: dict[str, Any] | None = None,
        config_path: str | Path | None = None,
        # Legacy / direct-constructor mode
        target_tool_name: str | None = None,
        warning_message: str | None = None,
        trigger_on_nth_call: int = 1,
    ) -> None:
        super().__init__()

        # --- Logging setup ---
        self.log_file: str | None = os.getenv("BFCL_EXTERNAL_FEEDBACK_LOG_FILE")
        if self.log_file:
            Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

        self.test_case_id: str = os.getenv("TEST_ID", "unknown")
        self.global_call_index: int = 0

        # Set of *normalised* tool names that have successfully passed through
        # (not blocked).  Used for precondition_missing matching.
        self.called_tools: set[str] = set()

        # --- Build trigger rules ---
        if config is not None or config_path is not None:
            self.triggers = self._load_config_triggers(config, config_path)
            self._stderr(
                f"[ExternalFeedbackMiddleware] Config mode: "
                f"{len(self.triggers)} trigger(s) loaded"
            )
            for i, rule in enumerate(self.triggers, 1):
                self._stderr(
                    f"[ExternalFeedbackMiddleware]   Rule {i}: "
                    f"{rule.trigger_type} on '{rule.tool_name}' "
                    f"(occurrence={rule.occurrence}, label={rule.condition_label})"
                )
        else:
            self.triggers = self._build_legacy_triggers(
                target_tool_name, warning_message, trigger_on_nth_call
            )

    # ------------------------------------------------------------------
    # Config / legacy builders
    # ------------------------------------------------------------------

    def _load_config_triggers(
        self,
        config: dict[str, Any] | None,
        config_path: str | Path | None,
    ) -> list[TriggerRule]:
        if config is None:
            assert config_path is not None
            with open(config_path) as fh:
                config = json.load(fh)
        rules: list[TriggerRule] = []
        for raw in config.get("triggers", []):
            tool_name: str = raw["tool_name"]
            rules.append(
                TriggerRule(
                    tool_name=tool_name,
                    tool_name_normalized=self._normalize(tool_name),
                    trigger_type=raw["trigger_type"],
                    argument_conditions=raw.get("argument_conditions"),
                    occurrence=int(raw["occurrence"]),
                    feedback_message=raw.get("feedback_message", ""),
                    condition_label=raw["condition_label"],
                )
            )
        return rules

    def _build_legacy_triggers(
        self,
        target_tool_name: str | None,
        warning_message: str | None,
        trigger_on_nth_call: int,
    ) -> list[TriggerRule]:
        """Construct a single tool_only rule from env vars / constructor args."""
        tool = target_tool_name or os.getenv("BFCL_EXTERNAL_FEEDBACK_TOOL", "")
        msg = warning_message or os.getenv("BFCL_EXTERNAL_FEEDBACK_MESSAGE", "")
        n = int(os.getenv("BFCL_EXTERNAL_FEEDBACK_N", str(trigger_on_nth_call)))
        self._stderr(
            f"[ExternalFeedbackMiddleware] Legacy mode: "
            f"watching '{tool}', trigger on call #{n}"
        )
        return [
            TriggerRule(
                tool_name=tool,
                tool_name_normalized=self._normalize(tool),
                trigger_type="tool_only",
                argument_conditions=None,
                occurrence=n,
                feedback_message=msg,
                condition_label="specific",
            )
        ]

    # ------------------------------------------------------------------
    # FastMCP hook
    # ------------------------------------------------------------------

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        msg = context.message
        self.global_call_index += 1
        args: dict[str, Any] = dict(msg.arguments or {})

        # Evaluate every unfired rule in order.
        for rule in self.triggers:
            if rule.fired:
                continue
            if not self._name_matches(msg.name, rule.tool_name_normalized):
                continue
            if not self._conditions_match(rule, args):
                continue

            rule.match_count += 1

            if rule.match_count == rule.occurrence:
                # ---- Trigger fires ----
                rule.fired = True
                self._write_log_record(
                    tool_name=msg.name,
                    arguments=args,
                    triggered=True,
                    rule=rule,
                )
                self._stderr(
                    f"[ExternalFeedbackMiddleware] ✓ TRIGGERED '{rule.trigger_type}' "
                    f"on '{msg.name}' "
                    f"(match #{rule.match_count}, label={rule.condition_label})"
                )

                raise ToolError(rule.feedback_message or "")

        # ---- No rule fired — pass through ----
        self._write_log_record(
            tool_name=msg.name,
            arguments=args,
            triggered=False,
            rule=None,
        )
        result = await call_next(context)
        # Only record as "called" after a successful pass-through.
        self.called_tools.add(self._normalize(msg.name))
        return result

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    def _name_matches(self, call_name: str, rule_normalized: str) -> bool:
        normalised = self._normalize(call_name)
        return normalised == rule_normalized or normalised.endswith(rule_normalized)

    def _conditions_match(self, rule: TriggerRule, args: dict[str, Any]) -> bool:
        """Return True when all non-name conditions for *rule* are satisfied."""
        t = rule.trigger_type
        cond: dict[str, Any] = rule.argument_conditions or {}

        if t == "tool_only":
            return True

        if t == "argument_present":
            forbidden: list[str] = cond.get("forbidden_args", [])
            return any(k in args for k in forbidden)

        if t == "argument_value":
            checks: list[dict[str, Any]] = cond.get("checks", [])
            match_mode: str = cond.get("match", "any")
            results = [self._evaluate_check(args, c) for c in checks]
            return all(results) if match_mode == "all" else any(results)

        if t == "precondition_missing":
            required: list[str] = cond.get("required_prior_calls", [])
            # Fires when at least one required prior tool has NOT yet passed through.
            return any(self._normalize(r) not in self.called_tools for r in required)

        self._stderr(
            f"[ExternalFeedbackMiddleware] Unknown trigger_type '{t}', skipping"
        )
        return False

    def _evaluate_check(self, args: dict[str, Any], check: dict[str, Any]) -> bool:
        """Evaluate a single argument_value check dict against *args*."""
        key: str = check["key"]
        op: str = check["op"]
        expected: Any = check["value"]

        if key not in args:
            return False

        actual: Any = args[key]

        try:
            match op:
                case "eq":
                    return bool(actual == expected)
                case "neq":
                    return bool(actual != expected)
                case "gt":
                    return bool(actual > expected)
                case "gte":
                    return bool(actual >= expected)
                case "lt":
                    return bool(actual < expected)
                case "lte":
                    return bool(actual <= expected)
                case "in":
                    return bool(actual in expected)
                case "not_in":
                    return bool(actual not in expected)
                case "contains":
                    if isinstance(actual, str):
                        return str(expected) in actual
                    if isinstance(actual, (list, tuple)):
                        return expected in actual
                    return False
                case _:
                    self._stderr(
                        f"[ExternalFeedbackMiddleware] Unknown op '{op}', "
                        "check skipped (returns False)"
                    )
                    return False
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------
    # Structured logging
    # ------------------------------------------------------------------

    def _write_log_record(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        triggered: bool,
        rule: TriggerRule | None,
    ) -> None:
        """Append one JSON line to the log file (if configured)."""
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test_case_id": self.test_case_id,
            "global_call_index": self.global_call_index,
            "tool_name": tool_name,
            "arguments": arguments,
            "triggered": triggered,
            "trigger_type": rule.trigger_type if rule else None,
            "condition_label": rule.condition_label if rule else None,
            "feedback_message": rule.feedback_message if rule else None,
            "occurrence": rule.match_count if rule else None,
        }

        status = "TRIGGERED" if triggered else "pass"
        self._stderr(
            f"[ExternalFeedbackMiddleware] "
            f"call #{self.global_call_index} '{tool_name}' -> {status}"
        )

        if self.log_file:
            try:
                with open(self.log_file, "a") as fh:
                    fh.write(json.dumps(record) + "\n")
                    fh.flush()
            except Exception as exc:
                self._stderr(
                    f"[ExternalFeedbackMiddleware] Log write error: {exc}"
                )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    @staticmethod
    def _stderr(message: str) -> None:
        print(message, file=sys.stderr, flush=True)
