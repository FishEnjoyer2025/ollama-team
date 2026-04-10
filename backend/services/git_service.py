import asyncio
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# The repo the agents work on is the ollama-team project itself
REPO_PATH = Path(__file__).parent.parent.parent

async def _run(cmd: str, cwd: Optional[Path] = None) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd or REPO_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

async def create_branch(name: str) -> bool:
    """Create and checkout a new branch."""
    code, out, err = await _run(f"git checkout -b {name}")
    if code != 0:
        logger.error(f"Failed to create branch {name}: {err}")
        return False
    logger.info(f"Created branch: {name}")
    return True

async def checkout(branch: str) -> bool:
    """Checkout an existing branch."""
    code, out, err = await _run(f"git checkout {branch}")
    if code != 0:
        logger.error(f"Failed to checkout {branch}: {err}")
        return False
    return True

async def current_branch() -> str:
    """Get the current branch name."""
    code, out, err = await _run("git branch --show-current")
    return out if code == 0 else "unknown"

async def commit(message: str, files: Optional[List[str]] = None) -> Optional[str]:
    """Stage files and commit. Returns commit hash or None on failure."""
    if files:
        for f in files:
            await _run(f'git add "{f}"')
    else:
        await _run("git add -A")

    code, out, err = await _run(f'git commit -m "{message}"')
    if code != 0:
        logger.error(f"Commit failed: {err}")
        return None

    code, sha, _ = await _run("git rev-parse HEAD")
    return sha if code == 0 else None

async def merge(branch: str, into: str = "main") -> bool:
    """Merge a branch into the target branch."""
    await checkout(into)
    code, out, err = await _run(f"git merge {branch} --no-edit")
    if code != 0:
        logger.error(f"Merge failed: {err}")
        # Abort the merge
        await _run("git merge --abort")
        return False
    logger.info(f"Merged {branch} into {into}")
    return True

async def revert(commit_hash: Optional[str] = None) -> bool:
    """Revert the last commit or a specific commit."""
    if commit_hash is None:
        code, out, err = await _run("git reset --hard HEAD~1")
        return code == 0
    else:
        code, out, err = await _run(f"git revert {commit_hash}")
        return code == 0

async def get_diff(branch: Optional[str] = None) -> str:
    """Get the diff of a branch or the working directory."""
    if branch is None:
        code, out, err = await _run("git diff")
    else:
        code, out, err = await _run(f"git diff {branch}")
    return out

async def get_staged_diff() -> str:
    """Get the diff of staged changes."""
    code, out, err = await _run("git diff --cached")
    return out