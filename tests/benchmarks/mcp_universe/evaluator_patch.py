"""
Evaluator patch module for v0.10.0 compatibility - fixes evaluator code bugs
"""
import re
from typing import Tuple
from mcpuniverse.evaluator import github
from mcpuniverse.evaluator import functions as eval_funcs


def apply_patch():
    """
    Apply patches to fix evaluator bugs that prevent tests from passing.

    Bugs fixed:
    1. Missing **kwargs in check_repository_with_fewest_issues
    2. fork:true query string comparison bug in github_check_repository
    3. Missing **kwargs in _get_groundtruth_repo_list
    """
    print("[PATCH] DISABLED - Testing without patches")
    return False
    # print("[PATCH] Applying evaluator bug fixes for v0.10.0 compatibility")

    # PATCH 1: Fix fork:true query parsing in github_check_repository
    async def patched_github_check_repository(x: dict, *args, **kwargs) -> Tuple[bool, str]:
        """Check whether a Github repository exists - with fork:true support."""
        _, query = args
        repos = await github.functions.github__check_repository(query, **kwargs)
        if repos is None or repos['total_count'] == 0:
            return False, "the repository doesn't exist"

        full_names = [repo['full_name'] for repo in repos['items']]

        # Extract repo name from query if it contains qualifiers like "repo:" or "fork:"
        match = re.search(r'repo:([^/]+/[^\s]+)', query)
        if match:
            expected_repo = match.group(1)
            if expected_repo in full_names:
                # If fork:true in query, verify it's actually a fork
                if 'fork:true' in query:
                    matching_repos = [r for r in repos['items'] if r['full_name'] == expected_repo]
                    if matching_repos and matching_repos[0].get('fork', False):
                        return True, ""
                    return False, "the repository is not a fork"
                return True, ""

        # Fallback to old logic for simple queries
        if query in full_names:
            return True, ""
        return False, "the repository doesn't exist"

    # PATCH 2: Fix missing **kwargs in check_repository_with_fewest_issues
    async def patched_check_repository_with_fewest_issues(x: dict, *args, **kwargs) -> Tuple[bool, str]:
        """Check if file content is valid and the number of issues is the fewest."""
        _, op_args = args
        repos = op_args['repos']
        owner = op_args['owner']
        # find the repo with the fewest issues
        fewest_issues_repo_name = None
        fewest_issues_count = float('inf')
        for repo in repos:
            repo_owner, repo_name = repo.split('/')
            # FIX: Pass **kwargs to github__list_issues
            issues = await github.functions.github__list_issues(
                repo_owner, repo_name, state=op_args['issue_state'], **kwargs
            )
            if issues is None:
                return False, f"the issues are not found for {repo_owner}/{repo_name}"
            if len(issues) < fewest_issues_count:
                fewest_issues_count = len(issues)
                fewest_issues_repo_name = repo_name

        # FIX: Pass **kwargs to github__check_repository
        repos_check = await github.functions.github__check_repository(
            f"repo:{owner}/{fewest_issues_repo_name} fork:true", **kwargs
        )

        if repos_check is None or repos_check['total_count'] == 0:
            return False, "the repository doesn't exist"
        full_names = [repo['full_name'] for repo in repos_check['items']]
        if f"{owner}/{fewest_issues_repo_name}" in full_names:
            return True, ""
        return False, "the repository doesn't exist"

    # PATCH 3: Fix missing **kwargs in check_file_content_with_fewest_issues
    async def patched_check_file_content_with_fewest_issues(x: dict, *args, **kwargs) -> Tuple[bool, str]:
        """Check if file content is valid and the number of issues is the fewest."""
        _, op_args = args
        repos = op_args['repos']
        owner = op_args['owner']
        # find the repo with the fewest issues
        fewest_issues_repo_name = None
        fewest_issues_count = float('inf')
        fewest_issues_repo_id = None
        for repo_id, repo in enumerate(repos):
            repo_owner, repo_name = repo.split('/')
            # FIX: Pass **kwargs to github__list_issues
            issues = await github.functions.github__list_issues(
                repo_owner, repo_name, state=op_args['issue_state'], **kwargs
            )
            if issues is None:
                return False, f"the issues are not found for {repo_owner}/{repo_name}"
            if len(issues) < fewest_issues_count:
                fewest_issues_count = len(issues)
                fewest_issues_repo_name = repo_name
                fewest_issues_repo_id = repo_id

        # FIX: Pass **kwargs to github__check_repository
        repos_check = await github.functions.github__check_repository(
            f"repo:{owner}/{fewest_issues_repo_name} fork:true", **kwargs
        )

        if repos_check is None or repos_check['total_count'] == 0:
            return False, "the repository doesn't exist"

        # FIX: Pass **kwargs to github__get_file_contents
        resp = await github.functions.github__get_file_contents(
            owner, fewest_issues_repo_name, op_args['path'], op_args['branch'], **kwargs
        )

        if resp is None:
            return False, "the file content is not found"

        # check if file content includes the expected content
        file_content = op_args['file_content']
        expected_file_content = file_content[fewest_issues_repo_id]

        if expected_file_content not in resp:
            return False, f"{resp} doesn't include {expected_file_content}"
        return True, ""

    # PATCH 4: Fix github_check_file_content_and_issue_count with **kwargs in nested function
    async def patched_github_check_file_content_and_issue_count(x: dict, *args, **kwargs) -> Tuple[bool, str]:
        """Check if file content is valid and the number of issues is correct."""
        import io
        import csv
        import json

        async def _get_groundtruth_repo_list(repo_owner, repo_name, issue_state, issue_labels):
            # FIX: Pass **kwargs to github__check_repository
            repo_list = await github.functions.github__check_repository(
                f"user:{repo_owner} {repo_name} in:name", **kwargs
            )
            if repo_list is None:
                return None
            ret = {}
            for repo in repo_list["items"]:
                repo_full_name = repo["full_name"]
                # FIX: Handle both formats - v0.10.0 has nested owner, v0.14.0+ doesn't
                if "owner" in repo:
                    repo_owner_login = repo["owner"]["login"]
                else:
                    repo_owner_login = repo_full_name.split("/")[0]

                repo_name_field = repo.get("name", repo_full_name.split("/")[1])

                # FIX: Pass **kwargs to github__list_issues
                issues = await github.functions.github__list_issues(
                    repo_owner_login, repo_name_field,
                    labels=issue_labels, state=issue_state, **kwargs
                )
                if issues is not None:
                    ret[repo_full_name] = len(issues)
            return ret

        def _get_file_content_to_dict(file_content, **op_args):
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

        _, op_args = args

        # get the groundtruth repo list
        gt_repo_list = await _get_groundtruth_repo_list(
            op_args['search_repo_owner'], op_args['search_repo_name'],
            op_args['issue_state'], op_args['issue_labels'])

        if gt_repo_list is None:
            return False, "the groundtruth repo list is not found"

        # get the csv file content - FIX: Pass **kwargs
        resp = await github.functions.github__get_file_contents(
            op_args['owner'], op_args['repo'], op_args['path'], op_args['branch'], **kwargs
        )

        if resp is None:
            return False, "the file content is not found"

        return_repo_list = _get_file_content_to_dict(resp, **op_args)

        # check if the return_repo_list is the same as the gt_repo_list
        if not return_repo_list == gt_repo_list:
            return False, (
                "the return_repo_list is not the same as the gt_repo_list!\n"
                f"## response:\n{return_repo_list} \n"
                f"## expected:\n{gt_repo_list}"
            )
        return True, ""

    # Apply patches - update both module functions AND COMPARISON_FUNCTIONS dictionary
    github.functions.github_check_repository = patched_github_check_repository
    github.functions.github_check_repository_with_fewest_issues = patched_check_repository_with_fewest_issues
    github.functions.github_check_file_content_with_fewest_issues = patched_check_file_content_with_fewest_issues
    github.functions.github_check_file_content_and_issue_count = patched_github_check_file_content_and_issue_count

    # Also update COMPARISON_FUNCTIONS dictionary
    eval_funcs.COMPARISON_FUNCTIONS["github.check_repository"] = patched_github_check_repository
    eval_funcs.COMPARISON_FUNCTIONS["github.check_repository_with_fewest_issues"] = patched_check_repository_with_fewest_issues
    eval_funcs.COMPARISON_FUNCTIONS["github.check_file_content_with_fewest_issues"] = patched_check_file_content_with_fewest_issues
    eval_funcs.COMPARISON_FUNCTIONS["github.check_file_content_and_issue_count"] = patched_github_check_file_content_and_issue_count

    print("[PATCH] ✓ Fixed fork:true query parsing in github_check_repository")
    print("[PATCH] ✓ Fixed missing **kwargs in check_repository_with_fewest_issues")
    print("[PATCH] ✓ Fixed missing **kwargs in check_file_content_with_fewest_issues")
    print("[PATCH] ✓ Fixed missing **kwargs and owner field handling in check_file_content_and_issue_count")

    return True
