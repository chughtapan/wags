"""
Evaluator patch for MCP-Universe with GitHub MCP Server v0.15.0.

Fixes evaluator bugs causing false negatives (model succeeds, evaluator fails).

PATCHED FUNCTIONS:
- github.check_file_content_and_issue_count (0007): KeyError 'owner', list_issues
- github.check_repository_with_fewest_issues (0025-0030): list_issues, search delay
- github.check_file_content_with_fewest_issues (0028-0030): list_issues, search delay
- github.check_repository (0006-0010, 0011, 0014, 0023-0024): fork:true parsing, search delay
- github.file_content_include (0014-0015): file content validation
- github.check_number_of_issues (0010, 0012, 0016-0019): list_issues failures

HELPERS:
- _github_api_list_issues: PR filtering, labels, pagination via direct REST API
- _github_api_check_repo_exists: direct API for new repos (avoids search indexing delay)
"""

import csv
import io
import json
import os
import re
from dataclasses import dataclass
from typing import Literal

import httpx
import mcpuniverse.evaluator.functions as evaluator_functions
import mcpuniverse.evaluator.github.functions as github_functions
from mcpuniverse.evaluator.github.functions import (
    github__check_repository,
    github__get_file_contents,
    github__get_issue_comments,
)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_TIMEOUT = 30.0
GITHUB_API_PAGE_SIZE = 100
GITHUB_API_MAX_PAGES = 40


# =============================================================================
# GitHub API Helpers
# =============================================================================


def _get_github_headers() -> dict[str, str] | None:
    """Get GitHub API headers with authentication token."""
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        return None
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


async def _github_api_check_repo_exists(owner: str, repo: str) -> bool:
    """Check if a repo exists via direct GitHub REST API."""
    headers = _get_github_headers()
    if not headers:
        return False

    async with httpx.AsyncClient(timeout=GITHUB_API_TIMEOUT) as client:
        try:
            response = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", headers=headers)
            return response.status_code == 200
        except (httpx.HTTPError, TimeoutError):
            return False


async def _github_api_list_issues(
    owner: str,
    repo: str,
    state: Literal["open", "closed", "all"] | None = "all",
    labels: list[str] | None = None,
) -> list[dict] | None:
    """List issues via direct GitHub REST API (bypasses MCP server rate limits)."""
    headers = _get_github_headers()
    if not headers:
        print("[PATCH] Warning: GITHUB_PERSONAL_ACCESS_TOKEN not set")
        return None

    params: dict = {"per_page": GITHUB_API_PAGE_SIZE}
    if state:
        params["state"] = state.lower()
    if labels:
        params["labels"] = ",".join(labels)

    all_issues = []
    async with httpx.AsyncClient(timeout=GITHUB_API_TIMEOUT) as client:
        for page in range(1, GITHUB_API_MAX_PAGES):
            params["page"] = page
            try:
                response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues", headers=headers, params=params
                )
                if response.status_code != 200:
                    return None

                issues = response.json()
                if not issues:
                    break

                is_last_page = len(issues) < GITHUB_API_PAGE_SIZE

                # Filter out PRs (GitHub issues API returns both)
                issues = [i for i in issues if "pull_request" not in i]

                # Filter to issues with NO labels when labels=[] (no API param for this)
                if labels is not None and len(labels) == 0:
                    issues = [i for i in issues if not i.get("labels")]

                all_issues.extend(issues)

                if is_last_page:
                    break
            except (httpx.HTTPError, TimeoutError, json.JSONDecodeError) as e:
                print(f"[PATCH] Error fetching issues for {owner}/{repo}: {e}")
                return None

    return all_issues


async def _check_repo_exists_with_fallback(owner: str, repo: str, **kwargs) -> bool:
    """Check if repo exists via direct API, fallback to search API."""
    if await _github_api_check_repo_exists(owner, repo):
        return True

    result = await github__check_repository(f"repo:{owner}/{repo} fork:true", **kwargs)
    if not result or result["total_count"] == 0:
        return False
    return f"{owner}/{repo}" in [r["full_name"] for r in result["items"]]


def _parse_file_content(file_content: str, file_type: str, csv_columns: list[str] | None = None) -> dict:
    """Parse file content (CSV or JSON) into a dict."""
    if file_type == "csv":
        if not csv_columns or len(csv_columns) != 2:
            raise ValueError("CSV requires exactly 2 columns")
        reader = csv.DictReader(io.StringIO(file_content))
        result = {}
        for row in reader:
            result[row[csv_columns[0]]] = int(row[csv_columns[1]])
        return result
    if file_type == "json":
        return json.loads(file_content)
    raise ValueError(f"Unsupported file type: {file_type}")


@dataclass
class IssueFilter:
    """Filter criteria for GitHub issues."""

    title: str | None = None
    labels: list[str] | None = None
    comments: str | None = None


async def _filter_issue(issue: dict, filter_opts: IssueFilter, owner: str, repo: str, **kwargs) -> bool:
    """Filter an issue by title, labels, and comments."""
    if filter_opts.title is not None and issue["title"] != filter_opts.title:
        return False
    if filter_opts.labels is not None:
        issue_labels = [lbl["name"] for lbl in issue["labels"]]
        if not all(lbl in issue_labels for lbl in filter_opts.labels):
            return False
    if filter_opts.comments is not None:
        issue_comments = await github__get_issue_comments(owner, repo, issue["number"], **kwargs)
        if issue_comments and not any(c["body"] == filter_opts.comments for c in issue_comments):
            return False
    return True


# =============================================================================
# Patched Evaluator Functions
# =============================================================================


async def _patched_check_file_content_and_issue_count(_: dict, *args, **kwargs) -> tuple[bool, str]:
    """Check if CSV/JSON file content matches issue counts across repos."""
    _, op_args = args

    # Build ground truth from search results
    repo_list = await github__check_repository(
        f"user:{op_args['search_repo_owner']} {op_args['search_repo_name']} in:name", **kwargs
    )
    if repo_list is None:
        return False, "the groundtruth repo list is not found"

    gt_repo_list = {}
    for repo in repo_list["items"]:
        full_name = repo["full_name"]
        try:
            owner_login, repo_name = repo["owner"]["login"], repo["name"]
        except (KeyError, TypeError):
            parts = full_name.split("/")
            if len(parts) != 2:
                continue
            owner_login, repo_name = parts

        issues = await _github_api_list_issues(
            owner_login, repo_name, state=op_args["issue_state"], labels=op_args["issue_labels"]
        )
        if issues is not None:
            gt_repo_list[full_name] = len(issues)

    # Get and parse file content
    resp = await github__get_file_contents(
        op_args["owner"], op_args["repo"], op_args["path"], op_args["branch"], **kwargs
    )
    if resp is None:
        return False, "the file content is not found"

    return_repo_list = _parse_file_content(resp, op_args["file_type"], op_args.get("csv_columns"))

    if return_repo_list != gt_repo_list:
        return False, (
            f"the return_repo_list is not the same as the gt_repo_list!\n"
            f"## response:\n{return_repo_list} \n## expected:\n{gt_repo_list}"
        )
    return True, ""


async def _find_repo_with_fewest_issues(
    repos: list[str], issue_state: str
) -> tuple[str | None, int | None]:
    """Find repo with fewest issues, returning (repo_name, index)."""
    fewest_repo, fewest_count, fewest_idx = None, float("inf"), None
    for idx, repo_full in enumerate(repos):
        repo_owner, repo_name = repo_full.split("/")
        issues = await _github_api_list_issues(repo_owner, repo_name, state=issue_state)
        if issues is not None and len(issues) < fewest_count:
            fewest_count = len(issues)
            fewest_repo = repo_name
            fewest_idx = idx
    return fewest_repo, fewest_idx


async def _patched_check_repository_with_fewest_issues(_: dict, *args, **kwargs) -> tuple[bool, str]:
    """Check if user forked the repo with fewest issues."""
    _, op_args = args
    owner = op_args["owner"]
    issue_state = op_args.get("issue_state", "all")

    fewest_repo, _ = await _find_repo_with_fewest_issues(op_args["repos"], issue_state)
    if fewest_repo is None:
        return False, "Could not determine repository with fewest issues"

    if await _check_repo_exists_with_fallback(owner, fewest_repo, **kwargs):
        return True, ""
    return False, f"Repository {owner}/{fewest_repo} doesn't exist"


async def _patched_check_file_content_with_fewest_issues(_: dict, *args, **kwargs) -> tuple[bool, str]:
    """Check if file content matches expected for repo with fewest issues."""
    _, op_args = args
    owner = op_args["owner"]
    issue_state = op_args.get("issue_state", "all")

    fewest_repo, fewest_idx = await _find_repo_with_fewest_issues(op_args["repos"], issue_state)
    if fewest_repo is None:
        return False, "Could not determine repository with fewest issues"

    if not await _check_repo_exists_with_fallback(owner, fewest_repo, **kwargs):
        return False, f"Repository {owner}/{fewest_repo} doesn't exist"

    resp = await github__get_file_contents(owner, fewest_repo, op_args["path"], op_args["branch"], **kwargs)
    expected = op_args["file_content"][fewest_idx]
    if resp and expected in resp:
        return True, ""
    return False, f"Content '{expected}' is not found in the file"


async def _patched_check_repository(_: dict, *args, **kwargs) -> tuple[bool, str]:
    """Check whether a GitHub repository exists."""
    _, query = args

    # Simple "owner/repo" format
    if "/" in query and " " not in query:
        parts = query.strip().split("/")
        if len(parts) == 2 and await _github_api_check_repo_exists(parts[0], parts[1]):
            return True, ""
        return False, "the repository doesn't exist"

    # "repo:owner/repo" format - try direct API first
    repo_match = re.search(r"repo:([^/]+)/([^\s]+)", query)
    if repo_match and await _github_api_check_repo_exists(repo_match.group(1), repo_match.group(2)):
        return True, ""

    # Fall back to search API
    repos = await github__check_repository(query, **kwargs)
    if not repos or repos["total_count"] == 0:
        return False, "the repository doesn't exist"

    full_names = [r["full_name"] for r in repos["items"]]
    if repo_match:
        expected = f"{repo_match.group(1)}/{repo_match.group(2)}"
        return (True, "") if expected in full_names else (False, f"Expected {expected}, found {full_names}")

    return (True, "") if full_names else (False, "the repository doesn't exist")


async def _patched_file_content_include(_: dict, *args, **kwargs) -> tuple[bool, str]:
    """Check if file content includes expected strings."""
    value, op_args = args
    owner, repo = op_args["owner"], op_args["repo"]

    resp = await github__get_file_contents(owner, repo, op_args["path"], op_args["branch"], **kwargs)
    if not resp:
        return False, f"the file {owner}/{repo}/{op_args['branch']}/{op_args['path']} doesn't exist"

    if value is None:
        return True, ""

    for expected in value:
        if expected not in resp:
            return False, f"{resp} doesn't include {expected}"
    return True, ""


async def _patched_check_number_of_issues(_: dict, *args, **kwargs) -> tuple[bool, str]:
    """Check the GitHub issues count matches expected."""
    value, op_args = args
    owner, repo = op_args["owner"], op_args["repo"]
    title = op_args.get("title")
    labels = op_args.get("labels")
    state = op_args.get("state")
    comments = op_args.get("comments")

    if comments and "[repo owner name]" in comments:
        comments = comments.replace("[repo owner name]", owner)

    issues = await _github_api_list_issues(owner, repo, state=state, labels=labels)
    if issues is None:
        return False, "the issues are not found"

    issue_filter = IssueFilter(title=title, labels=labels, comments=comments)
    filtered = [i for i in issues if await _filter_issue(i, issue_filter, owner, repo, **kwargs)]

    if len(filtered) == value:
        return True, ""
    return False, (
        f'the number of filtered issues [title:"{title}", labels:{labels}] is wrong\n'
        f"## response:\n{len(filtered)} \n## expected:\n{value}"
    )


# =============================================================================
# Patch Application
# =============================================================================


def apply_patch() -> bool:
    """Apply patches to MCP-Universe evaluator for GitHub MCP Server v0.15.0 compatibility."""
    patches = {
        "check_file_content_and_issue_count": _patched_check_file_content_and_issue_count,
        "check_repository_with_fewest_issues": _patched_check_repository_with_fewest_issues,
        "check_file_content_with_fewest_issues": _patched_check_file_content_with_fewest_issues,
        "check_repository": _patched_check_repository,
        "file_content_include": _patched_file_content_include,
        "check_number_of_issues": _patched_check_number_of_issues,
    }

    # Patch both the module functions and the COMPARISON_FUNCTIONS registry
    for name, func in patches.items():
        setattr(github_functions, f"github_{name}", func)
        evaluator_functions.COMPARISON_FUNCTIONS[f"github.{name}"] = func

    return True
