"""Mock GitHub server with GroupsMiddleware for E2E testing."""

from typing import Any

from fastmcp import FastMCP

from wags.middleware.groups import GroupDefinition, GroupsMiddleware, in_group
from wags.proxy import create_proxy

server = FastMCP("mock-github")


class GithubHandlers:
    @in_group("repo_management")
    async def create_repository(self, name: str, private: bool = False) -> None:
        pass

    @in_group("branches")
    async def create_branch(self, repo: str, branch_name: str) -> None:
        pass

    @in_group("branches")
    async def list_branches(self, repo: str) -> None:
        pass

    @in_group("issues")
    async def create_issue(self, title: str, body: str) -> None:
        pass

    @in_group("issues")
    async def list_issues(self) -> None:
        pass

    @in_group("pull_requests")
    async def create_pull_request(self, title: str, head: str, base: str) -> None:
        pass


@server.tool()
async def create_repository(name: str, private: bool = False) -> dict[str, Any]:
    """Create a new repository."""
    return {"id": 123, "name": name, "private": private, "created": True}


@server.tool()
async def create_branch(repo: str, branch_name: str) -> dict[str, Any]:
    """Create a new branch."""
    return {"repo": repo, "branch_name": branch_name, "created": True}


@server.tool()
async def list_branches(repo: str) -> list[dict[str, Any]]:
    """List all branches."""
    return [
        {"name": "main", "protected": True},
        {"name": "develop", "protected": False},
    ]


@server.tool()
async def create_issue(title: str, body: str) -> dict[str, Any]:
    """Create a new issue."""
    return {"id": 1, "title": title, "body": body, "state": "open"}


@server.tool()
async def list_issues() -> list[dict[str, Any]]:
    """List all issues."""
    return [
        {"id": 1, "title": "Issue 1", "state": "open"},
        {"id": 2, "title": "Issue 2", "state": "closed"},
    ]


@server.tool()
async def create_pull_request(title: str, head: str, base: str) -> dict[str, Any]:
    """Create a pull request."""
    return {"id": 10, "title": title, "head": head, "base": base, "state": "open"}


# Group hierarchy:
#   code_management (root)
#     - repo_management
#       - branches (3 levels deep)
#     - pull_requests
#   issues (root, independent)
proxy = create_proxy(server, server_name="mock-github-groups")
proxy.add_middleware(
    GroupsMiddleware(
        groups={
            "code_management": GroupDefinition(description="Code and repository management"),
            "repo_management": GroupDefinition(description="Repository creation", parent="code_management"),
            "branches": GroupDefinition(description="Branch management", parent="repo_management"),
            "pull_requests": GroupDefinition(description="Pull request management", parent="code_management"),
            "issues": GroupDefinition(description="Issue tracking"),
        },
        handlers=GithubHandlers(),
        initial_groups=[],
        max_tools=6,
    )
)

mcp = proxy
