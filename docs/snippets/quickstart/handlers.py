from typing import Annotated

from wags.middleware import RequiresElicitation, requires_root


class GitHubHandlers:
    async def search_repositories(self, query: str, limit: int = 10):
        # Search method is safe: nothing to be done
        pass

    # Ensure that client has enabled access to this repository
    @requires_root("https://github.com/{owner}/{repo}")
    async def get_repository(self, owner: str, repo: str):
        pass

    @requires_root("https://github.com/{owner}/{repo}")
    async def create_issue(
        self,
        owner: str,
        repo: str,
        # Allow user to review and edit these fields
        # before actually invoking the tool
        title: Annotated[str, RequiresElicitation(
            "Title")],
        body: Annotated[str, RequiresElicitation(
            "Body"
        )]
    ):
        pass
