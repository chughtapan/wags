from typing import Annotated, Any, Literal

from wags.middleware import RequiresElicitation, requires_root

# Note: This is a handlers class for use with ElicitationMiddleware
# Usage: middleware = ElicitationMiddleware(handlers=GithubHandlers())


class GithubHandlers:
    """Auto-generated handlers for MCP server."""
    @requires_root("https://github.com/{owner}/{repo}")
    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: Annotated[str, RequiresElicitation(
            "What content should be written to this file?"
        )],
        message: Annotated[str, RequiresElicitation(
            "What should the commit message be? (Describe what changed and why)"
        )],
        branch: str,
        sha: str | None = None
    ):
        """Create or update a single file in a GitHub repository"""
        pass

    async def search_repositories(
        self,
        query: str,
        page: float | None = None,
        perPage: float | None = None
    ):
        """Search for GitHub repositories"""
        pass

    async def create_repository(
        self,
        name: str,
        description: str | None = None,
        private: bool | None = False,
        autoInit: bool | None = False
    ):
        """Create a new GitHub repository in your account"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str | None = None
    ):
        """Get the contents of a file or directory from a GitHub repository"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def push_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        files: list[dict[str, Any]],
        message: Annotated[str, RequiresElicitation(
            "What should the commit message be for these file changes?"
        )]
    ):
        """Push multiple files to a GitHub repository in a single commit"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: Annotated[str, RequiresElicitation(
            "What should the issue title be? (Be concise and descriptive)"
        )],
        body: Annotated[str | None, RequiresElicitation(
            "What should the issue body contain? (Provide details, context, and any relevant information)"
        )] = None,
        assignees: list[str] | None = None,
        milestone: float | None = None,
        labels: list[str] | None = None
    ):
        """Create a new issue in a GitHub repository"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: Annotated[str, RequiresElicitation(
            "What should the PR title be? (Describe the changes concisely)"
        )],
        head: str,
        base: str,
        body: Annotated[str | None, RequiresElicitation(
            "What should the PR description include? (Explain what changed, why, and any testing done)"
        )] = None,
        draft: bool | None = False,
        maintainer_can_modify: bool | None = False
    ):
        """Create a new pull request in a GitHub repository"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def fork_repository(
        self,
        owner: str,
        repo: str,
        organization: str | None = None
    ):
        """Fork a GitHub repository to your account or specified organization"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
        from_branch: str | None = None
    ):
        """Create a new branch in a GitHub repository"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def list_commits(
        self,
        owner: str,
        repo: str,
        sha: str | None = None,
        page: float | None = None,
        perPage: float | None = None
    ):
        """Get list of commits of a branch in a GitHub repository"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def list_issues(
        self,
        owner: str,
        repo: str,
        direction: Literal["asc", "desc"] | None = None,
        labels: list[str] | None = None,
        page: float | None = None,
        per_page: float | None = None,
        since: str | None = None,
        sort: Literal["created", "updated", "comments"] | None = None,
        state: Literal["open", "closed", "all"] | None = None
    ):
        """List issues in a GitHub repository with filtering options"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: float,
        title: str | None = None,
        body: Annotated[str | None, RequiresElicitation(
            "What should the updated issue body be?"
        )] = None,
        assignees: list[str] | None = None,
        milestone: float | None = None,
        labels: list[str] | None = None,
        state: Literal["open", "closed"] | None = None
    ):
        """Update an existing issue in a GitHub repository"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def add_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: float,
        body: Annotated[str, RequiresElicitation(
            "What comment would you like to add to this issue?"
        )]
    ):
        """Add a comment to an existing issue"""
        pass

    async def search_code(
        self,
        q: str,
        order: Literal["asc", "desc"] | None = None,
        page: float | None = None,
        per_page: float | None = None
    ):
        """Search for code across GitHub repositories"""
        pass

    async def search_issues(
        self,
        q: str,
        order: Literal["asc", "desc"] | None = None,
        page: float | None = None,
        per_page: float | None = None,
        sort: Literal["comments", "reactions", "reactions-+1", "reactions--1", "reactions-smile", "reactions-thinking_face", "reactions-heart", "reactions-tada", "interactions", "created", "updated"] | None = None
    ):
        """Search for issues and pull requests across GitHub repositories"""
        pass

    async def search_users(
        self,
        q: str,
        order: Literal["asc", "desc"] | None = None,
        page: float | None = None,
        per_page: float | None = None,
        sort: Literal["followers", "repositories", "joined"] | None = None
    ):
        """Search for users on GitHub"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_issue(
        self,
        owner: str,
        repo: str,
        issue_number: float
    ):
        """Get details of a specific issue in a GitHub repository."""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: float
    ):
        """Get details of a specific pull request"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: Literal["open", "closed", "all"] | None = None,
        head: str | None = None,
        base: str | None = None,
        sort: Literal["created", "updated", "popularity", "long-running"] | None = None,
        direction: Literal["asc", "desc"] | None = None,
        per_page: float | None = None,
        page: float | None = None
    ):
        """List and filter repository pull requests"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_pull_request_review(
        self,
        owner: str,
        repo: str,
        pull_number: float,
        body: Annotated[str, RequiresElicitation(
            "What should your review comment say? (Provide constructive feedback)"
        )],
        event: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"],
        commit_id: str | None = None,
        comments: list[Any] | None = None
    ):
        """Create a review on a pull request"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: float,
        commit_title: Annotated[str | None, RequiresElicitation(
            "What should the merge commit title be? (Leave blank for default)"
        )] = None,
        commit_message: Annotated[str | None, RequiresElicitation(
            "What should the merge commit message be? (Leave blank for default)"
        )] = None,
        merge_method: Literal["merge", "squash", "rebase"] | None = None
    ):
        """Merge a pull request"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_pull_request_files(
        self,
        owner: str,
        repo: str,
        pull_number: float
    ):
        """Get the list of files changed in a pull request"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_pull_request_status(
        self,
        owner: str,
        repo: str,
        pull_number: float
    ):
        """Get the combined status of all status checks for a pull request"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def update_pull_request_branch(
        self,
        owner: str,
        repo: str,
        pull_number: float,
        expected_head_sha: str | None = None
    ):
        """Update a pull request branch with the latest changes from the base branch"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_pull_request_comments(
        self,
        owner: str,
        repo: str,
        pull_number: float
    ):
        """Get the review comments on a pull request"""
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def get_pull_request_reviews(
        self,
        owner: str,
        repo: str,
        pull_number: float
    ):
        """Get the reviews on a pull request"""
        pass