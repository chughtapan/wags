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
See ``experiments/parth/feedback_ablation/configs/`` for examples.  Top-level fields::

    subset        – "A" … "G"
    condition     – "specific" | "vague" | "verbose" | "null"
    description   – optional human note (ignored at runtime)
    test_ids      – list of BFCL test IDs this config applies to
    triggers      – list of trigger-rule objects (see TriggerRule)

Each trigger-rule object::

    tool_name           – (str, required) target tool, name-normalised on match
    trigger_type        – "tool_only" | "argument_present"
                          | "argument_value" | "precondition_missing"
                          | "precondition_check"
    argument_conditions – (object, optional) shape varies by trigger_type
    condition           – (str, optional) for precondition_check only
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

precondition_check
    Evaluates a named condition against tracked execution state.
    Requires ``condition`` field on the trigger rule.  Supported conditions:

    cd_to_current_dir
        Fires if the cd target matches the current working directory.
    duplicate_ls_no_state_change
        Fires if ls was already called with the same arguments and no
        state-mutating tool has run since.
    arg_not_recent_file
        Fires if the ``file_name`` argument is not in the set of files
        recently involved in mv/cp/cat/grep calls.
    mv_dest_missing_directory
        Fires if the mv ``destination`` contains no ``/`` and does not
        match any directory name from the most recent ls output.
    mkdir_already_exists
        Fires if ``dir_name`` matches a directory in the last ls output
        or the last component of the current cwd.
    echo_content_extra_quotes
        Fires if the ``content`` argument starts and ends with matching
        quote characters (``'…'`` or ``"…"``).
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
    trigger_type: str  # tool_only | argument_present | argument_value | precondition_missing | precondition_check
    argument_conditions: dict[str, Any] | None
    condition: str | None  # precondition_check condition name (e.g. cd_to_current_dir)
    occurrence: int
    feedback_message: str
    condition_label: str

    # Runtime counters — mutated during execution, not sourced from config.
    match_count: int = field(default=0, init=False)
    fired: bool = field(default=False, init=False)


# Tools whose execution changes filesystem state (used by precondition_check).
STATE_MUTATING_TOOLS: frozenset[str] = frozenset(
    {"mv", "mkdir", "echo", "cd", "cp", "rm", "touch", "rmdir", "cat"}
)


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

        # --- Tracked execution state (for precondition_check triggers) ---
        initial_cwd = os.getenv("BFCL_INITIAL_CWD")
        self.cwd: str | None = initial_cwd
        self.last_ls_result: str | None = None
        self.last_ls_args: dict[str, Any] | None = None
        self.state_changed_since_last_ls: bool = False
        self.recent_files: set[str] = set()
        if initial_cwd:
            self._stderr(
                f"[ExternalFeedbackMiddleware] Initial cwd seeded: {initial_cwd}"
            )

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
                    condition=raw.get("condition"),
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
                condition=None,
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

            matched, precondition_state = self._conditions_match(rule, args)
            if not matched:
                # Log the non-match for precondition_check rules (useful for debugging).
                if rule.trigger_type == "precondition_check" and precondition_state:
                    self._write_log_record(
                        tool_name=msg.name,
                        arguments=args,
                        triggered=False,
                        rule=rule,
                        precondition_state=precondition_state,
                    )
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
                    precondition_state=precondition_state,
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
        # Update tracked execution state from the result.
        self._update_tracked_state(msg.name, args, result)
        return result

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    def _name_matches(self, call_name: str, rule_normalized: str) -> bool:
        normalised = self._normalize(call_name)
        return normalised == rule_normalized or normalised.endswith(rule_normalized)

    def _conditions_match(
        self, rule: TriggerRule, args: dict[str, Any],
    ) -> tuple[bool, dict[str, Any] | None]:
        """Return (matched, precondition_state) for *rule*.

        ``precondition_state`` is non-None only for ``precondition_check``
        rules and contains the values that were compared (for logging).
        """
        t = rule.trigger_type
        cond: dict[str, Any] = rule.argument_conditions or {}

        if t == "tool_only":
            return True, None

        if t == "argument_present":
            forbidden: list[str] = cond.get("forbidden_args", [])
            return any(k in args for k in forbidden), None

        if t == "argument_value":
            checks: list[dict[str, Any]] = cond.get("checks", [])
            match_mode: str = cond.get("match", "any")
            results = [self._evaluate_check(args, c) for c in checks]
            matched = all(results) if match_mode == "all" else any(results)
            return matched, None

        if t == "precondition_missing":
            required: list[str] = cond.get("required_prior_calls", [])
            # Fires when at least one required prior tool has NOT yet passed through.
            return any(self._normalize(r) not in self.called_tools for r in required), None

        if t == "precondition_check":
            return self._evaluate_precondition(rule, args)

        self._stderr(
            f"[ExternalFeedbackMiddleware] Unknown trigger_type '{t}', skipping"
        )
        return False, None

    # ------------------------------------------------------------------
    # Precondition-check evaluation
    # ------------------------------------------------------------------

    def _evaluate_precondition(
        self, rule: TriggerRule, args: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate a precondition_check rule against tracked state."""
        condition = rule.condition

        if condition == "cd_to_current_dir":
            target = args.get("folder", args.get("path", ""))
            matched = self._is_same_dir(target)
            state = {
                "condition": condition,
                "condition_met": matched,
                "cwd": self.cwd,
                "cd_target": target,
            }
            return matched, state

        if condition == "duplicate_ls_no_state_change":
            same_args = self.last_ls_args is not None and args == self.last_ls_args
            matched = (
                self.last_ls_result is not None
                and not self.state_changed_since_last_ls
                and same_args
            )
            state = {
                "condition": condition,
                "condition_met": matched,
                "last_ls_result_exists": self.last_ls_result is not None,
                "state_changed_since_last_ls": self.state_changed_since_last_ls,
                "same_args": same_args,
                "last_ls_args": self.last_ls_args,
                "current_args": args,
            }
            return matched, state

        if condition == "arg_not_recent_file":
            file_name = args.get("file_name", "")
            matched = bool(file_name and file_name not in self.recent_files)
            state = {
                "condition": condition,
                "condition_met": matched,
                "file_name": file_name,
                "recent_files": sorted(self.recent_files),
            }
            return matched, state

        if condition == "mv_dest_missing_directory":
            dest = args.get("destination", "")
            has_slash = "/" in dest
            ls_dirs = self._parse_ls_directories()
            in_ls = dest in ls_dirs if ls_dirs is not None else False
            matched = bool(dest and not has_slash and not in_ls)
            state = {
                "condition": condition,
                "condition_met": matched,
                "destination": dest,
                "has_slash": has_slash,
                "ls_directories": sorted(ls_dirs) if ls_dirs is not None else None,
                "dest_in_ls": in_ls,
            }
            return matched, state

        if condition == "mkdir_already_exists":
            dir_name = args.get("dir_name", "")
            cwd_name = self.cwd.rstrip("/").rsplit("/", 1)[-1] if self.cwd else None
            ls_dirs = self._parse_ls_directories()
            in_ls = dir_name in ls_dirs if ls_dirs is not None else False
            is_cwd = bool(cwd_name and dir_name == cwd_name)
            matched = in_ls or is_cwd
            state = {
                "condition": condition,
                "condition_met": matched,
                "dir_name": dir_name,
                "cwd_name": cwd_name,
                "in_ls_dirs": in_ls,
                "matches_cwd": is_cwd,
            }
            return matched, state

        if condition == "echo_content_extra_quotes":
            content = args.get("content", "")
            matched = (
                len(content) >= 2
                and (
                    (content[0] == "'" and content[-1] == "'")
                    or (content[0] == '"' and content[-1] == '"')
                )
            )
            state = {
                "condition": condition,
                "condition_met": matched,
                "content_preview": content[:60] + ("…" if len(content) > 60 else ""),
                "starts_with": content[0] if content else None,
                "ends_with": content[-1] if content else None,
            }
            return matched, state

        self._stderr(
            f"[ExternalFeedbackMiddleware] Unknown precondition_check "
            f"condition '{condition}', skipping"
        )
        return False, {"condition": condition, "condition_met": False, "error": "unknown"}

    def _is_same_dir(self, target: str) -> bool:
        """Check whether *target* resolves to the current working directory."""
        if self.cwd is None:
            return False
        if not target or target == ".":
            return True
        cwd_name = self.cwd.rstrip("/").rsplit("/", 1)[-1]
        target_clean = target.rstrip("/")
        if target_clean == cwd_name:
            return True
        if target_clean.startswith("/"):
            return target_clean.rstrip("/") == self.cwd.rstrip("/")
        import posixpath
        resolved = posixpath.normpath(posixpath.join(self.cwd, target_clean))
        return resolved == posixpath.normpath(self.cwd)

    # ------------------------------------------------------------------
    # Tracked state updates
    # ------------------------------------------------------------------

    def _update_tracked_state(
        self, tool_name: str, args: dict[str, Any], result: ToolResult,
    ) -> None:
        """Update cwd / ls / mutation / file tracking from a successful tool result."""
        norm = self._normalize(tool_name)
        text = self._extract_result_text(result)

        if norm in {"cd", "chdir"}:
            cwd = self._parse_json_field(text, "current_working_directory")
            if cwd:
                self.cwd = cwd
            self.state_changed_since_last_ls = True

        elif norm == "pwd":
            cwd = self._parse_json_field(text, "current_working_directory")
            if cwd:
                self.cwd = cwd

        elif norm == "ls":
            self.last_ls_result = text
            self.last_ls_args = dict(args)
            self.state_changed_since_last_ls = False

        if norm in STATE_MUTATING_TOOLS:
            self.state_changed_since_last_ls = True

        # Track files involved in file-manipulation tools.
        if norm in {"mv", "cp"}:
            for key in ("source", "destination"):
                val = args.get(key, "")
                if val:
                    self.recent_files.add(val.rsplit("/", 1)[-1])
        elif norm in {"cat", "grep"}:
            val = args.get("file_name", "")
            if val:
                self.recent_files.add(val.rsplit("/", 1)[-1])

    @staticmethod
    def _extract_result_text(result: ToolResult) -> str:
        """Pull the concatenated text from a ToolResult."""
        parts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts)

    @staticmethod
    def _parse_json_field(text: str, field: str) -> str | None:
        """Try to extract a top-level JSON field from *text*."""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data.get(field)
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    def _parse_ls_directories(self) -> set[str] | None:
        """Extract directory names from the last ls result.

        The GorillaFileSystem ls returns JSON with a
        ``current_directory_content`` list of names.  We can't
        distinguish files from directories by name alone, so we return
        all entries — the caller treats them as potential directory names.
        """
        if self.last_ls_result is None:
            return None
        items = self._parse_json_field(self.last_ls_result, "current_directory_content")
        if isinstance(items, list):
            return {str(i) for i in items}
        return None

    # ------------------------------------------------------------------
    # Argument-value checks
    # ------------------------------------------------------------------

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
        precondition_state: dict[str, Any] | None = None,
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
        if precondition_state is not None:
            record["precondition_state"] = precondition_state

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
