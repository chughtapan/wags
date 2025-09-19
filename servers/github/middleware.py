"""
Example of GitHub middleware with elicitation for key text fields.

This is a simplified example showing how to add elicitation to the
most commonly used GitHub tools that create content.
"""

from typing import Annotated, Any, Literal

from wags.middleware.base import tool_handler
from wags.middleware.elicitation import ElicitationMiddleware, RequiresElicitation


class GithubElicitationMiddleware(ElicitationMiddleware):
    """GitHub middleware with elicitation for content creation."""

    @tool_handler
    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: Annotated[str, RequiresElicitation(
            "What should the issue title be? (Be concise and descriptive)"
        )],
        assignees: list[str] | None = None,
        body: Annotated[str | None, RequiresElicitation(
            "What should the issue body contain? (Provide details, context, and any relevant information)"
        )] = None,
        labels: list[str] | None = None,
        milestone: float | None = None,
        type: str | None = None
    ):
        """Create a new issue in a GitHub repository."""
        pass

    @tool_handler
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
        """Create a new pull request in a GitHub repository."""
        pass

    @tool_handler
    async def add_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: float,
        body: Annotated[str, RequiresElicitation(
            "What comment would you like to add to this issue?"
        )]
    ):
        """Add a comment to a specific issue in a GitHub repository."""
        pass

    @tool_handler
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
        """Create or update a single file in a GitHub repository."""
        pass

    @tool_handler
    async def create_and_submit_pull_request_review(
        self,
        owner: str,
        repo: str,
        pullNumber: float,
        body: Annotated[str, RequiresElicitation(
            "What should your review comment say? (Provide constructive feedback)"
        )],
        event: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"],
        commitID: str | None = None
    ):
        """Create and submit a review for a pull request without review comments."""
        pass

    # Add remaining methods from the generated file as needed...
    # The full generated middleware has 93 tools - this is just an example
    # showing how to add elicitation to the most common text fields