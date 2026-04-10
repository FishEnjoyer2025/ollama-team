import asyncio
import logging
from backend.services import git_service
from backend.services.health import check_health

logger = logging.getLogger(__name__)


class DeployerAgent:
    """Deployer is mostly scripted — minimal LLM involvement.
    Handles git operations, service restarts, and rollbacks."""

    name = "deployer"

    async def create_branch(self, description: str) -> str:
        """Create a feature branch for an improvement."""
        import time
ts = int(time.time())
        # Sanitize description for branch name
        slug = description[:40].lower()
        slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug)
        slug = slug.strip("-")
        branch_name = f"improve/{slug}-{ts}"

        success = await git_service.create_branch(branch_name)
        if not success:
            logger.error(f"Failed to create branch: {branch_name}")
            raise RuntimeError(f"Failed to create branch: {branch_name}")
        return branch_name

    async def commit_changes(self, message: str, files: list[str] = None) -> str:
        """Commit current changes. Returns commit hash."""
        sha = await git_service.commit(message, files)
        if not sha:
            logger.error("Failed to commit changes")
            raise RuntimeError("Failed to commit changes")
        return sha

    async def merge_to_main(self, branch: str) -> bool:
        """Merge feature branch into main."""
        success = await git_service.merge(branch, "main")
        if success:
            # Clean up the feature branch
            await git_service.delete_branch(branch)
        return success

    async def verify_health(self) -> bool:
        """Check system health after deploy."""
        return await check_health()

    async def rollback(self, reason: str) -> bool:
        """Revert the last commit on main."""
        logger.warning(f"Rolling back: {reason}")
        await git_service.checkout("main")
        success = await git_service.revert()
        if success:
            logger.info("Rollback successful")
        else:
            logger.error("Rollback failed!")
        return success

    async def restart_backend(self) -> bool:
        """Restart the backend service.

        In practice this signals the orchestrator to reload.
        Full process restart would be handled by supervisor/systemd.
        """
        logger.info("Backend restart requested (handled by process manager)")
        # The orchestrator checks for t