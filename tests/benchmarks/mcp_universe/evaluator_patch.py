"""
Patch for MCP-Universe evaluator to handle GitHub MCP server v0.15.0 incompatibilities.

This patch fixes multiple issues with the GitHub MCP server v0.15.0:

1. **KeyError 'owner' bug**: Search results use minimal_output format without nested 'owner' object.
   Fix: Extract owner/repo from 'full_name' field (e.g., "facebook/react" -> "facebook", "react")

2. **list_issues incompatibility**: The list_issues tool returns None when filtering by labels.
   Fix: Replace all list_issues calls with search_issues which works correctly.

3. **GitHub Actions timing**: Comments are added asynchronously by workflows.
   Fix: Add retry logic with exponential backoff (3s, 6s, 10s)

4. **Function signature mismatch**: Evaluator passes 3 positional args but docs suggest keyword arg.
   Fix: Handle both calling conventions (2-arg and 3-arg)

5. **NoneType len() error**: API failures return None which caused crashes.
   Fix: Add None checks before calling len() on API results
"""

import asyncio
import json
from typing import Optional, Tuple


def extract_owner_and_repo(repo_data: dict) -> tuple[str, str]:
    """
    Extract owner and repo name from repository data.

    Handles both formats:
    - Full format: repo["owner"]["login"] and repo["name"]
    - Minimal format: Parse from repo["full_name"] (e.g., "microsoft/AirSim")

    Args:
        repo_data: Repository data dict from search_repositories

    Returns:
        Tuple of (owner, repo_name)
    """
    # Try full format first
    if "owner" in repo_data and "login" in repo_data["owner"]:
        return repo_data["owner"]["login"], repo_data["name"]

    # Fall back to minimal format: parse full_name
    if "full_name" in repo_data:
        parts = repo_data["full_name"].split("/")
        if len(parts) == 2:
            return parts[0], parts[1]

    # Last resort: try name field alone
    if "name" in repo_data:
        return "unknown", repo_data["name"]

    raise ValueError(f"Cannot extract owner/repo from data: {repo_data}")


async def github__search_issues(owner: str, repo: str, state: str = None,
                                 labels: list = None, title: str = None,
                                 return_count_only: bool = False, **kwargs):
    """
    Search for issues using the GitHub MCP server's search_issues tool.

    This replaces list_issues which is incompatible with GitHub MCP server v0.15.0.
    The search_issues tool works correctly with label filtering.

    Args:
        owner: Repository owner
        repo: Repository name
        state: Issue state ('open', 'closed', or 'all')
        labels: List of label names to filter by
        title: Issue title to filter by (exact match)
        return_count_only: If True, return total_count as int. If False, return dict with total_count and items.
        **kwargs: Must contain 'context' with MCPManager

    Returns:
        If return_count_only=True: int (total count) or None on error
        If return_count_only=False: list of issue dicts, or None on error
    """
    from mcpuniverse.mcp.manager import MCPManager

    manager = MCPManager(context=kwargs.get("context", None))

    # Build search query in GitHub search syntax
    query_parts = [f"repo:{owner}/{repo}", "is:issue"]

    if state and state != "all":
        query_parts.append(f"is:{state}")

    if labels:
        for label in labels:
            query_parts.append(f'label:"{label}"')

    if title:
        query_parts.append(f'"{title}" in:title')

    query = " ".join(query_parts)

    try:
        # First, get total_count with minimal data transfer
        output = await manager.execute(
            server_name="github",
            tool_name="search_issues",
            arguments={"query": query, "perPage": 1},
            transport="stdio"
        )
        if output.isError:
            return None

        # Parse JSON result
        result_data = json.loads(output.content[0].text)
        total_count = result_data.get("total_count", 0)

        # If caller only needs count (for groundtruth), return it immediately
        if return_count_only:
            return total_count

        # If zero results, return empty list
        if total_count == 0:
            return []

        # Otherwise, fetch first 100 issues for filtering
        # Note: If >100 issues need filtering by comments, results may be incomplete
        # But GitHub MCP search query already filters by title/labels, so this should be rare
        output = await manager.execute(
            server_name="github",
            tool_name="search_issues",
            arguments={"query": query, "perPage": 100},
            transport="stdio"
        )
        if output.isError:
            return None
        result_data = json.loads(output.content[0].text)
        return result_data.get("items", [])
    except Exception as e:
        print(f"[PATCH] Error in github__search_issues: {e}")
        return None


def apply_patch():
    """
    Apply monkey patch to MCP-Universe evaluator functions to handle minimal format and timing issues.

    CRITICAL: Must patch BOTH the functions module AND the COMPARISON_FUNCTIONS dictionary
    that the Evaluator class uses to look up functions.
    """
    try:
        from mcpuniverse.evaluator.github import functions
        from mcpuniverse.evaluator.functions import COMPARISON_FUNCTIONS

        # ===== PATCH 1: Fix KeyError 'owner' bug =====
        # Store original function
        original_check_file_content_and_issue_count = functions.github_check_file_content_and_issue_count

        # Create patched version
        async def patched_github_check_file_content_and_issue_count(x: dict, *args, **kwargs):
            """Patched version that handles minimal_output format."""
            from mcpuniverse.mcp.manager import MCPManager
            import csv
            import io

            # Handle both calling conventions:
            # - func(x, value, op_args, context=ctx) -> args=(value, op_args), kwargs={'context': ctx}
            # - func(x, value, op_args, ctx) -> args=(value, op_args, ctx), kwargs={}
            if len(args) == 3:
                value, op_args, context_arg = args
                if 'context' not in kwargs:
                    kwargs['context'] = context_arg
            elif len(args) == 2:
                value, op_args = args
            else:
                raise ValueError(f"Unexpected number of positional arguments: {len(args)}")

            async def _get_groundtruth_repo_list(repo_owner, repo_name, issue_state, issue_labels):
                """Fixed version that uses search_issues instead of broken list_issues."""
                import datetime
                print(f"\n{'='*80}")
                print(f"[GROUND TRUTH COMPUTATION] {datetime.datetime.now().isoformat()}")
                print(f"{'='*80}")
                print(f"Computing expected counts by querying GitHub API...")
                print(f"Search query: 'user:{repo_owner} {repo_name} in:name'")
                print(f"Issue filters: state={issue_state}, labels={issue_labels}")
                print(f"{'='*80}\n")

                repo_list = await functions.github__check_repository(
                    f"user:{repo_owner} {repo_name} in:name",
                    **kwargs
                )
                if repo_list is None:
                    print(f"[PATCH] ❌ Repository search returned None\n")
                    return None

                print(f"[PATCH] Found {len(repo_list['items'])} repositories matching pattern")
                print(f"[PATCH] Counting issues for each repository...\n")

                ret = {}
                for i, repo in enumerate(repo_list["items"], 1):
                    repo_full_name = repo["full_name"]
                    # FIX: Use our extraction function instead of assuming owner object exists
                    owner, repo_name_parsed = extract_owner_and_repo(repo)

                    # Build search query
                    search_query = f"repo:{owner}/{repo_name_parsed} is:issue"
                    if issue_state and issue_state != "all":
                        search_query += f" is:{issue_state}"
                    if issue_labels:
                        for label in issue_labels:
                            search_query += f' label:"{label}"'

                    print(f"[{i}/{len(repo_list['items'])}] {repo_full_name}")
                    print(f"      Query: {search_query}")

                    # FIX: Use search_issues with return_count_only=True to get accurate total (even if >100)
                    issue_count = await github__search_issues(
                        owner, repo_name_parsed,
                        labels=issue_labels, state=issue_state, return_count_only=True, **kwargs
                    )
                    # Handle case where search_issues returns None (API error)
                    if issue_count is None:
                        print(f"      Result: None (API error) - treating as 0")
                        ret[repo_full_name] = 0
                    else:
                        print(f"      Result: {issue_count} issues")
                        ret[repo_full_name] = issue_count

                print(f"\n[GROUND TRUTH COMPUTATION COMPLETE]")
                print(f"Total repositories: {len(ret)}")
                print(f"{'='*80}\n")
                return ret

            def _get_file_content_to_dict(file_content, **op_args):
                """Parse file content into dict format."""
                file_type = op_args['file_type']
                if file_type == "csv":
                    csv_file = io.StringIO(file_content)
                    reader = csv.DictReader(csv_file)
                    return_repo_list = {}
                    for row in reader:
                        csv_columns = op_args['csv_columns']
                        assert len(csv_columns) == 2, "the number of columns should be 2"
                        repository_name = row[csv_columns[0]]
                        return_repo_list[repository_name] = int(row[csv_columns[1]])
                    return return_repo_list
                if file_type == "json":
                    return json.loads(file_content)
                raise ValueError(f"Unsupported file type: {file_type}")

            # Get the groundtruth repo list using patched function
            print(f"\n{'='*80}")
            print(f"[EVALUATOR] Checking File Content and Issue Counts")
            print(f"{'='*80}")
            print(f"Agent's File: {op_args['owner']}/{op_args['repo']}/{op_args['path']}")
            print(f"Search Criteria:")
            print(f"  - Repo Owner: {op_args['search_repo_owner']}")
            print(f"  - Repo Name Pattern: {op_args['search_repo_name']}")
            print(f"  - Issue State: {op_args['issue_state']}")
            print(f"  - Issue Labels: {op_args['issue_labels']}")
            print(f"{'='*80}\n")

            gt_repo_list = await _get_groundtruth_repo_list(
                op_args['search_repo_owner'], op_args['search_repo_name'],
                op_args['issue_state'], op_args['issue_labels'])

            if gt_repo_list is None:
                print(f"[PATCH] ❌ FAILED: Groundtruth repo list not found\n")
                return False, "the groundtruth repo list is not found"

            print(f"[PATCH] ✓ Ground truth computed for {len(gt_repo_list)} repositories")

            # Get file content from agent's created repository
            import datetime
            print(f"\n{'='*80}")
            print(f"[AGENT FILE PARSING] {datetime.datetime.now().isoformat()}")
            print(f"{'='*80}")
            print(f"Reading agent's output file...")
            print(f"File path: {op_args['owner']}/{op_args['repo']}/{op_args['path']}")
            if op_args.get('branch'):
                print(f"Branch: {op_args['branch']}")
            print(f"{'='*80}\n")

            file_content = await functions.github__get_file_contents(
                op_args['owner'], op_args['repo'], op_args['path'],
                branch=op_args.get('branch'), **kwargs)

            if file_content is None:
                print(f"[PATCH] ❌ FAILED: File not found at {op_args['owner']}/{op_args['repo']}/{op_args['path']}\n")
                return False, "the file content is not found"

            print(f"[PATCH] ✓ File retrieved successfully")
            print(f"[PATCH] File size: {len(file_content)} characters")
            print(f"[PATCH] File type: {op_args['file_type']}")
            print(f"[PATCH] Parsing file content...\n")

            # Parse file and compare with groundtruth
            agent_repo_list = _get_file_content_to_dict(file_content, **op_args)

            print(f"[PATCH] ✓ Agent's file parsed: {len(agent_repo_list)} repositories found")
            print(f"[AGENT FILE PARSING COMPLETE]")
            print(f"{'='*80}\n")
            print(f"\n{'='*80}")
            print(f"COMPARISON: Expected vs Actual")
            print(f"{'='*80}")

            # Show all repos in both lists
            all_repos = set(list(gt_repo_list.keys()) + list(agent_repo_list.keys()))
            matches = 0
            mismatches = 0
            for repo in sorted(all_repos):
                expected = gt_repo_list.get(repo, "NOT IN EXPECTED")
                actual = agent_repo_list.get(repo, "NOT IN ACTUAL")
                status = "✓" if expected == actual else "✗"
                if expected == actual:
                    matches += 1
                else:
                    mismatches += 1
                print(f"{status} {repo}:")
                print(f"    Expected: {expected} issues")
                print(f"    Actual:   {actual}")

            print(f"{'='*80}")
            print(f"Summary: {matches} matches, {mismatches} mismatches")
            print(f"{'='*80}\n")

            if gt_repo_list == agent_repo_list:
                print(f"[PATCH] ✅ SUCCESS: All repository counts match!\n")
                return True, ""
            else:
                print(f"[PATCH] ❌ FAILED: Repository counts don't match\n")
                return False, f"repo list doesn't match. Expected: {gt_repo_list}, Got: {agent_repo_list}"

        # Apply patch 1 to BOTH places
        functions.github_check_file_content_and_issue_count = patched_github_check_file_content_and_issue_count
        COMPARISON_FUNCTIONS["github.check_file_content_and_issue_count"] = patched_github_check_file_content_and_issue_count

        # ===== PATCH 2: Fix "Issues Not Found" bug with retry logic =====
        original_check_number_of_issues = functions.github_check_number_of_issues

        async def patched_github_check_number_of_issues(x: dict, *args, **kwargs) -> Tuple[bool, str]:
            """
            Patched version with retry logic and better error handling.

            Issues may not be immediately available due to:
            1. GitHub API indexing delays
            2. GitHub Actions workflows adding comments take time
            3. API rate limiting or temporary errors
            """

            async def _filter(issue: dict, condition: dict, owner: str, repo: str):
                """Filter issue by title, labels, and comments."""
                if "title" in condition and condition["title"] is not None:
                    if issue["title"] != condition["title"]:
                        return False
                if "labels" in condition and condition["labels"] is not None:
                    labels = [label['name'] for label in issue['labels']]
                    if not all(ele in labels for ele in condition["labels"]):
                        return False
                if "comments" in condition and condition["comments"] is not None:
                    comments_list = await functions.github__get_issue_comments(owner, repo, issue['number'], **kwargs)
                    if comments_list is None:
                        # Comments couldn't be retrieved - treat as not matching
                        return False
                    if not any(comment['body'] == condition["comments"] for comment in comments_list):
                        return False
                return True

            # Handle both calling conventions:
            # - func(x, value, op_args, context=ctx) -> args=(value, op_args), kwargs={'context': ctx}
            # - func(x, value, op_args, ctx) -> args=(value, op_args, ctx), kwargs={}
            if len(args) == 3:
                value, op_args, context_arg = args
                if 'context' not in kwargs:
                    kwargs['context'] = context_arg
            elif len(args) == 2:
                value, op_args = args
            else:
                raise ValueError(f"Unexpected number of positional arguments: {len(args)}")

            title = op_args.get('title', None)
            labels = op_args.get('labels', None)
            state = op_args.get('state', None)
            comments = op_args.get('comments', None)
            if comments and "[repo owner name]" in comments:
                comments = comments.replace("[repo owner name]", op_args['owner'])

            # Retry logic: Try up to 3 times with exponential backoff
            max_retries = 3
            retry_delays = [3, 6, 10]  # seconds

            print(f"\n{'='*80}")
            print(f"[EVALUATOR] Checking Issue Count")
            print(f"{'='*80}")
            print(f"Repository: {op_args['owner']}/{op_args['repo']}")
            print(f"EXPECTED: {value} issue(s)")
            print(f"FILTERS:")
            print(f"  - Title: {title if title else 'Any'}")
            print(f"  - Labels: {labels if labels else 'Any'}")
            print(f"  - State: {state if state else 'Any'}")
            print(f"  - Comments: {comments if comments else 'Any'}")
            print(f"{'='*80}\n")

            for attempt in range(max_retries):
                # Get issues from repository using search_issues (list_issues is broken on GitHub MCP v0.15.0)
                issues = await github__search_issues(
                    op_args['owner'], op_args['repo'], state=state, labels=labels, title=title, **kwargs
                )

                # If search_issues returns None, it's an error - retry
                if issues is None:
                    print(f"[PATCH] ❌ Issues search returned None")
                    if attempt < max_retries - 1:
                        print(f"[PATCH] ⏳ Retrying in {retry_delays[attempt]}s (attempt {attempt + 1}/{max_retries})...")
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    else:
                        print(f"[PATCH] ❌ FAILED: Issues not found after {max_retries} retries\n")
                        return False, "the issues are not found (search_issues returned None after retries)"

                # Filter issues by title, labels, comments
                filter_args = {
                    "title": title,
                    "labels": labels,
                    "comments": comments
                }

                filtered_issues = []
                for issue in issues:
                    if await _filter(issue, filter_args, op_args['owner'], op_args['repo']):
                        filtered_issues.append(issue)

                print(f"[PATCH] Found {len(issues)} total issues, {len(filtered_issues)} match filters")
                if filtered_issues:
                    print(f"[PATCH] MATCHED ISSUES:")
                    for i, issue in enumerate(filtered_issues, 1):
                        issue_labels = [l['name'] for l in issue.get('labels', [])]
                        print(f"  {i}. #{issue['number']}: '{issue['title']}' (labels: {issue_labels})")
                else:
                    print(f"[PATCH] No issues matched the filters")

                # Check if count matches
                if len(filtered_issues) == value:
                    print(f"[PATCH] ✅ SUCCESS: Found exactly {value} matching issue(s)\n")
                    return True, ""

                # If not enough issues found and we have retries left, wait and try again
                # (GitHub Actions might still be running)
                if len(filtered_issues) < value and attempt < max_retries - 1:
                    print(f"[PATCH] ⏳ Found {len(filtered_issues)}/{value} issues, retrying in {retry_delays[attempt]}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(retry_delays[attempt])
                    continue

                # Final attempt or found too many issues
                print(f"[PATCH] ❌ FAILED: Found {len(filtered_issues)} issues, expected {value}")
                print(f"{'='*80}\n")
                return False, (
                    f"the number of filtered issues [title:\"{title}\", labels:{labels}, comments:{comments}] is wrong\\n"
                    f"## response:\\n{len(filtered_issues)} issues found\\n"
                    f"## expected:\\n{value} issues"
                )

            # Should never reach here, but just in case
            return False, "the issues are not found (max retries exceeded)"

        # Apply patch 2 to BOTH places
        functions.github_check_number_of_issues = patched_github_check_number_of_issues
        COMPARISON_FUNCTIONS["github.check_number_of_issues"] = patched_github_check_number_of_issues

        print("[PATCH] Applied evaluator patches for GitHub MCP server v0.15.0 compatibility:")
        print("[PATCH]   1. Fixed KeyError 'owner' - Parse from 'full_name' field")
        print("[PATCH]   2. Fixed list_issues incompatibility - Replaced with search_issues")
        print("[PATCH]   3. Added retry logic for issue checks (handles GitHub Actions timing)")
        print("[PATCH]   4. Fixed function signature mismatch (2-arg and 3-arg support)")
        print("[PATCH]   5. Fixed NoneType len() error - Added None checks")
        print("[PATCH] All patches applied to both functions module and COMPARISON_FUNCTIONS dict")
        return True

    except ImportError as e:
        print(f"[PATCH] Warning: Could not import mcpuniverse: {e}")
        return False
    except Exception as e:
        print(f"[PATCH] Error applying patch: {e}")
        return False
