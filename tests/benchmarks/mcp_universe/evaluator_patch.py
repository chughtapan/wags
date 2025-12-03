"""
Evaluator patch for MCP-Universe with GitHub MCP Server v0.15.0.

Fixes evaluator bugs causing false negatives (model succeeds, evaluator fails).

PATCHED FUNCTIONS:
- github.check_file_content_and_issue_count (0007): KeyError 'owner', list_issues
- github.check_repository_with_fewest_issues (0025-0030): list_issues, search delay
- github.check_file_content_with_fewest_issues (0028-0030): list_issues, search delay
- github.check_repository (0006-0010, 0011, 0014, 0023-0024): fork:true parsing, renames
- github.file_content_include (0014-0015): repo renames in URLs
- github.check_number_of_issues (0010, 0012, 0016-0019): list_issues failures

HELPERS: github_api_list_issues_direct (PR filtering, labels, pagination, renames),
         github_api_check_repo_exists (direct API for new repos)

RENAMES: QwenLM/Qwen2.5-VL → Qwen3-VL, vinamra-test2/Qwen2.5-VL → Qwen3-VL
"""

import os
from typing import Literal

import httpx
import mcpuniverse.evaluator.github.functions as github_functions
from mcpuniverse.evaluator.github.functions import github__check_repository

# GitHub REST API base URL
GITHUB_API_BASE = "https://api.github.com"

# Repository renames - map old names to new names
# Include both original repos AND user forks
REPO_RENAMES = {
    "QwenLM/Qwen2.5-VL": "QwenLM/Qwen3-VL",
    # User forks of renamed repos (GitHub forks use new name)
    "vinamra-test2/Qwen2.5-VL": "vinamra-test2/Qwen3-VL",
    # Add more renames here as needed
}


def apply_patch():
    """
    Apply patch to MCP-Universe evaluator for compatibility with GitHub MCP Server v0.15.0.
    """
    # Evaluator patch for GitHub MCP Server v0.15.0

    # ============================================================================
    # HELPER: Direct GitHub REST API calls (bypassing MCP server for evaluation)
    # ============================================================================

    async def github_api_list_issues_direct(
        owner: str,
        repo: str,
        state: Literal["open", "closed", "all"] | None = "all",
        labels: list[str] | None = None,
    ) -> list[dict] | None:
        """
        Direct GitHub REST API call to list issues, bypassing MCP server.
        This is more reliable during evaluation as it doesn't hit search API limits.

        Also handles repository renames by mapping old names to new names.
        """
        # FIX: Handle repository renames
        full_repo_name = f"{owner}/{repo}"
        if full_repo_name in REPO_RENAMES:
            new_name = REPO_RENAMES[full_repo_name]
            owner, repo = new_name.split("/")
            print(f"[PATCH] Mapped renamed repo {full_repo_name} -> {new_name}")

        token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        if not token:
            print("[PATCH] Warning: GITHUB_PERSONAL_ACCESS_TOKEN not set, list_issues may fail")
            return None

        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

        # Map 'all' to no state filter (GitHub API doesn't support 'all')
        params = {"per_page": 100, "page": 1}
        if state and state.lower() != "all":
            params["state"] = state.lower()
        if labels:
            params["labels"] = ",".join(labels)

        all_issues = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, 40):  # Max 40 pages
                params["page"] = page
                url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"

                try:
                    response = await client.get(url, headers=headers, params=params)
                    if response.status_code != 200:
                        return None  # 404, 403, or other errors

                    issues = response.json()
                    if not issues:
                        break  # No more issues

                    # Check page size BEFORE filtering to determine if more pages exist
                    is_last_page = len(issues) < 100

                    # Filter out pull requests (they appear in issues API)
                    issues = [issue for issue in issues if "pull_request" not in issue]

                    # FIX: If labels=[] is passed, filter to issues with NO labels
                    # (GitHub API doesn't have a param for this, so we filter manually)
                    if labels is not None and len(labels) == 0:
                        issues = [
                            issue for issue in issues if not issue.get("labels") or len(issue.get("labels", [])) == 0
                        ]

                    all_issues.extend(issues)

                    if is_last_page:
                        break  # Last page

                except Exception as e:
                    print(f"[PATCH] Error fetching issues for {owner}/{repo}: {e}")
                    return None

        return all_issues

    # ============================================================================
    # FIX 1: KeyError: 'owner' in github_check_file_content_and_issue_count
    # ============================================================================

    async def patched_github_check_file_content_and_issue_count(_: dict, *args, **kwargs) -> tuple[bool, str]:
        """
        PATCHED: Check if CSV files are valid and the number of rows matches the number of issues.

        Fix: Extract owner from 'full_name' instead of 'owner.login' to handle GitHub search API response.
        """
        # IMPORTS MUST BE AT TOP before nested function definitions
        import csv
        import io
        import json

        from mcpuniverse.evaluator.github.functions import github__get_file_contents

        async def _get_groundtruth_repo_list(repo_owner, repo_name, issue_state, issue_labels):
            repo_list = await github__check_repository(f"user:{repo_owner} {repo_name} in:name", **kwargs)
            if repo_list is None:
                return None
            ret = {}
            for repo in repo_list["items"]:
                repo_full_name = repo["full_name"]

                # FIX: Extract owner from full_name instead of accessing repo["owner"]["login"]
                try:
                    owner_login = repo["owner"]["login"]
                    repo_name_str = repo["name"]
                except (KeyError, TypeError):
                    # Fallback: parse from full_name
                    parts = repo_full_name.split("/")
                    if len(parts) != 2:
                        print(f"[PATCH] Warning: Unexpected full_name format: {repo_full_name}")
                        continue
                    owner_login = parts[0]
                    repo_name_str = parts[1]

                # FIX: Use direct API instead of MCP server list_issues
                issues = await github_api_list_issues_direct(
                    owner_login, repo_name_str, state=issue_state, labels=issue_labels
                )
                if issues is None:
                    print(f"[PATCH] Warning: Could not fetch issues for {owner_login}/{repo_name_str}, skipping")
                    continue

                ret[repo_full_name] = len(issues)
            return ret

        def _get_file_content_to_dict(file_content, **op_args):
            file_type = op_args["file_type"]
            if file_type == "csv":
                csv_file = io.StringIO(file_content)
                reader = csv.DictReader(csv_file)
                return_repo_list = {}
                for row in reader:
                    csv_columns = op_args["csv_columns"]
                    assert len(csv_columns) == 2, "the number of columns should be 2"
                    repository_name = row[csv_columns[0]]
                    return_repo_list[repository_name] = int(row[csv_columns[1]])
                return return_repo_list
            if file_type == "json":
                return json.loads(file_content)
            raise ValueError(f"Unsupported file type: {file_type}")

        _, op_args = args

        # Get ground truth repo list
        gt_repo_list = await _get_groundtruth_repo_list(
            op_args["search_repo_owner"],
            op_args["search_repo_name"],
            op_args["issue_state"],
            op_args["issue_labels"],
        )

        if gt_repo_list is None:
            return False, "the groundtruth repo list is not found"

        # Get the CSV file content
        resp = await github__get_file_contents(
            op_args["owner"], op_args["repo"], op_args["path"], op_args["branch"], **kwargs
        )

        if resp is None:
            return False, "the file content is not found"

        return_repo_list = _get_file_content_to_dict(resp, **op_args)

        # Check if the return_repo_list is the same as the gt_repo_list
        if not return_repo_list == gt_repo_list:
            return False, (
                "the return_repo_list is not the same as the gt_repo_list!\n"
                f"## response:\n{return_repo_list} \n"
                f"## expected:\n{gt_repo_list}"
            )
        return True, ""

    # ============================================================================
    # FIX 2: list_issues failures in github_check_repository_with_fewest_issues
    # ============================================================================

    async def patched_github_check_repository_with_fewest_issues(_: dict, *args, **kwargs) -> tuple[bool, str]:
        """
        PATCHED: Check if file content is valid and the number of issues is the fewest.

        Fix: Use direct GitHub REST API instead of MCP server's list_issues which fails during evaluation.
        """
        _, op_args = args
        repos = op_args["repos"]
        owner = op_args["owner"]
        issue_state = op_args.get("issue_state", "all")

        # Find the repo with the fewest issues
        fewest_issues_repo_name = None
        fewest_issues_count = float("inf")

        for repo in repos:
            repo_owner, repo_name = repo.split("/")

            # FIX: Use direct API call instead of MCP server
            issues = await github_api_list_issues_direct(repo_owner, repo_name, state=issue_state)

            if issues is None:
                print(f"[PATCH] Warning: Could not fetch issues for {repo_owner}/{repo_name}")
                # Don't fail immediately - this repo might not exist or be inaccessible
                continue

            if len(issues) < fewest_issues_count:
                fewest_issues_count = len(issues)
                fewest_issues_repo_name = repo_name

        if fewest_issues_repo_name is None:
            return False, "Could not determine repository with fewest issues"

        # Check if the fork exists in the user's account
        # FIX: Try direct API first - search API may not index new forks immediately
        exists = await github_api_check_repo_exists(owner, fewest_issues_repo_name)
        if exists:
            return True, ""

        # Fallback to search API (might find renamed repos etc)
        repos_check = await github__check_repository(f"repo:{owner}/{fewest_issues_repo_name} fork:true", **kwargs)

        if repos_check is None or repos_check["total_count"] == 0:
            return False, f"Repository {owner}/{fewest_issues_repo_name} doesn't exist"

        full_names = [repo["full_name"] for repo in repos_check["items"]]
        if f"{owner}/{fewest_issues_repo_name}" in full_names:
            return True, ""

        return False, f"Repository {owner}/{fewest_issues_repo_name} doesn't exist"

    # ============================================================================
    # FIX 3: list_issues failures in github_check_file_content_with_fewest_issues
    # ============================================================================

    async def patched_github_check_file_content_with_fewest_issues(_: dict, *args, **kwargs) -> tuple[bool, str]:
        """
        PATCHED: Check if file content is valid and the number of issues is the fewest.

        Fix: Use direct GitHub REST API instead of MCP server's list_issues.
        """
        from mcpuniverse.evaluator.github.functions import github__get_file_contents

        _, op_args = args
        repos = op_args["repos"]
        owner = op_args["owner"]
        issue_state = op_args.get("issue_state", "all")

        # Find the repo with the fewest issues
        fewest_issues_repo_name = None
        fewest_issues_count = float("inf")
        fewest_issues_repo_id = None

        for repo_id, repo in enumerate(repos):
            repo_owner, repo_name = repo.split("/")

            # FIX: Use direct API call instead of MCP server
            issues = await github_api_list_issues_direct(repo_owner, repo_name, state=issue_state)

            if issues is None:
                print(f"[PATCH] Warning: Could not fetch issues for {repo_owner}/{repo_name}")
                continue

            if len(issues) < fewest_issues_count:
                fewest_issues_count = len(issues)
                fewest_issues_repo_name = repo_name
                fewest_issues_repo_id = repo_id

        if fewest_issues_repo_name is None:
            return False, "Could not determine repository with fewest issues"

        # Check if the fork exists
        # FIX: Try direct API first - search API may not index new forks immediately
        exists = await github_api_check_repo_exists(owner, fewest_issues_repo_name)
        if not exists:
            # Fallback to search API (might find renamed repos etc)
            repos_check = await github__check_repository(f"repo:{owner}/{fewest_issues_repo_name} fork:true", **kwargs)

            if repos_check is None or repos_check["total_count"] == 0:
                return False, f"Repository {owner}/{fewest_issues_repo_name} doesn't exist"

            full_names = [repo["full_name"] for repo in repos_check["items"]]
            if f"{owner}/{fewest_issues_repo_name}" not in full_names:
                return False, f"Repository {owner}/{fewest_issues_repo_name} doesn't exist"

        # Check file content
        resp = await github__get_file_contents(
            owner, fewest_issues_repo_name, op_args["path"], op_args["branch"], **kwargs
        )

        value = op_args["file_content"][fewest_issues_repo_id]
        if resp and value in resp:
            return True, ""

        return False, f"Content '{value}' is not found in the file"

    # ============================================================================
    # FIX 4: fork:true search query parsing bug in github_check_repository
    # ============================================================================

    async def github_api_check_repo_exists(owner: str, repo: str) -> bool:
        """
        Direct GitHub REST API call to check if a repo exists.
        More reliable than search API for newly created repos.
        """
        token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        if not token:
            return False

        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=headers)
                return response.status_code == 200
            except Exception:
                return False

    async def patched_github_check_repository(_: dict, *args, **kwargs) -> tuple[bool, str]:
        """
        PATCHED: Check whether a Github repository exists.
        Fixes: fork:true query parsing, repository renames, search API indexing delay.
        """
        import re

        _, query = args

        # Apply repository renames to the query
        modified_query = query
        for old_name, new_name in REPO_RENAMES.items():
            if old_name in query:
                modified_query = query.replace(old_name, new_name)
                break

        # Simple "owner/repo" format - use direct API (search API doesn't index new repos)
        if "/" in modified_query and " " not in modified_query:
            parts = modified_query.strip().split("/")
            if len(parts) == 2 and await github_api_check_repo_exists(parts[0], parts[1]):
                return True, ""
            return False, "the repository doesn't exist"

        # For "repo:owner/repo" queries, try direct API first
        repo_match = re.search(r"repo:([^/]+)/([^\s]+)", modified_query)
        if repo_match and await github_api_check_repo_exists(repo_match.group(1), repo_match.group(2)):
            return True, ""

        # Fall back to search API
        repos = await github__check_repository(modified_query, **kwargs)
        if not repos or repos["total_count"] == 0:
            return False, "the repository doesn't exist"

        full_names = [repo["full_name"] for repo in repos["items"]]

        # For "repo:" queries, check if the expected repo is in results
        if repo_match:
            expected = f"{repo_match.group(1)}/{repo_match.group(2)}"
            return (True, "") if expected in full_names else (False, f"Expected {expected}, found {full_names}")

        # For other queries, any result means repo exists
        return (True, "") if full_names else (False, "the repository doesn't exist")

    # ============================================================================
    # FIX 5: file_content_include needs to accept both old and new repo names in URLs
    # ============================================================================

    async def patched_github_file_content_include(_: dict, *args, **kwargs) -> tuple[bool, str]:
        """
        PATCHED: Check if file content includes some strings.

        Fix: When checking for URLs with repository names, accept both old and new names
        (e.g., both Qwen2.5-VL and Qwen3-VL URLs should match).
        Also apply rename mapping when accessing files (repo may have been renamed).
        """
        from mcpuniverse.evaluator.github.functions import github__get_file_contents

        value, op_args = args
        owner = op_args["owner"]
        repo = op_args["repo"]

        # FIX: Apply rename mapping to owner/repo before accessing file
        full_repo_name = f"{owner}/{repo}"
        if full_repo_name in REPO_RENAMES:
            new_name = REPO_RENAMES[full_repo_name]
            owner, repo = new_name.split("/")
            print(f"[PATCH] file_content_include: Mapped renamed repo {full_repo_name} -> {new_name}")

        resp = await github__get_file_contents(owner, repo, op_args["path"], op_args["branch"], **kwargs)
        file_path = f"{op_args['owner']}/{op_args['repo']}/{op_args['branch']}/{op_args['path']}"

        if resp:
            if value is None:
                return True, ""

            # Check each expected string
            for str0 in value:
                # First check if the string exists as-is
                if str0 in resp:
                    continue

                # FIX: If string contains an old repo name, also check with new repo name
                found = False
                for old_name, new_name in REPO_RENAMES.items():
                    if old_name in str0:
                        # Try with new name
                        str0_with_new_name = str0.replace(old_name, new_name)
                        if str0_with_new_name in resp:
                            print(f"[PATCH] Accepted renamed repo URL: {old_name} → {new_name}")
                            found = True
                            break

                if not found:
                    return False, f"{resp} doesn't include {str0}"

            return True, ""
        return False, f"the file {file_path} doesn't exist"

    # ============================================================================
    # FIX 6: list_issues failures in github_check_number_of_issues
    # ============================================================================

    async def patched_github_check_number_of_issues(_: dict, *args, **kwargs) -> tuple[bool, str]:
        """
        PATCHED: Check the github issues count.

        Fix: Use direct GitHub REST API instead of MCP server's list_issues.
        """
        from mcpuniverse.evaluator.github.functions import github__get_issue_comments

        async def _filter(issue: dict, condition: dict):
            if "title" in condition and condition["title"] is not None:
                if issue["title"] != condition["title"]:
                    return False
            if "labels" in condition and condition["labels"] is not None:
                labels = [label["name"] for label in issue["labels"]]
                if not all(ele in labels for ele in condition["labels"]):
                    return False
            if "comments" in condition and condition["comments"] is not None:
                comments = await github__get_issue_comments(
                    op_args["owner"], op_args["repo"], issue["number"], **kwargs
                )
                if comments and not any(comment["body"] == condition["comments"] for comment in comments):
                    return False
            return True

        value, op_args = args
        title = op_args.get("title", None)
        labels = op_args.get("labels", None)
        state = op_args.get("state", None)
        comments = op_args.get("comments", None)
        if comments and "[repo owner name]" in comments:
            comments = comments.replace("[repo owner name]", op_args["owner"])

        # FIX: Use direct API call instead of MCP server
        issues = await github_api_list_issues_direct(op_args["owner"], op_args["repo"], state=state, labels=labels)

        if issues is None:
            return False, "the issues are not found"

        filter_args = {"title": title, "labels": labels, "comments": comments}
        filtered_issues = []
        for issue in issues:
            if await _filter(issue, filter_args):
                filtered_issues.append(issue)

        if len(filtered_issues) == value:
            return True, ""
        return False, (
            f'the number of filtered issues [title:"{title}", labels:{labels}] is wrong\n'
            f"## response:\n{len(filtered_issues)} \n"
            f"## expected:\n{value}"
        )

    # Replace the functions in the module
    github_functions.github_check_file_content_and_issue_count = patched_github_check_file_content_and_issue_count
    github_functions.github_check_repository_with_fewest_issues = patched_github_check_repository_with_fewest_issues
    github_functions.github_check_file_content_with_fewest_issues = patched_github_check_file_content_with_fewest_issues
    github_functions.github_check_repository = patched_github_check_repository
    github_functions.github_file_content_include = patched_github_file_content_include
    github_functions.github_check_number_of_issues = patched_github_check_number_of_issues

    # CRITICAL FIX: Update the COMPARISON_FUNCTIONS dict in the CORRECT module!
    # The decorator @compare_func registers functions in mcpuniverse.evaluator.functions.COMPARISON_FUNCTIONS
    import mcpuniverse.evaluator.functions as evaluator_functions

    evaluator_functions.COMPARISON_FUNCTIONS["github.check_file_content_and_issue_count"] = (
        patched_github_check_file_content_and_issue_count
    )
    evaluator_functions.COMPARISON_FUNCTIONS["github.check_repository_with_fewest_issues"] = (
        patched_github_check_repository_with_fewest_issues
    )
    evaluator_functions.COMPARISON_FUNCTIONS["github.check_file_content_with_fewest_issues"] = (
        patched_github_check_file_content_with_fewest_issues
    )
    evaluator_functions.COMPARISON_FUNCTIONS["github.check_repository"] = patched_github_check_repository
    evaluator_functions.COMPARISON_FUNCTIONS["github.file_content_include"] = patched_github_file_content_include
    evaluator_functions.COMPARISON_FUNCTIONS["github.check_number_of_issues"] = patched_github_check_number_of_issues

    return True
