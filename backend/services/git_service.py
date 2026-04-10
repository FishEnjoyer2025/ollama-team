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
        code, _, err = await _run("git reset --hard HEAD~1")
        if code != 0:
            logger.error(f"Revert failed: {err}")
            return False
    else:
        code, _, err = await _run(f"git revert "{commit_hash}"")
        if code != 0:
            logger.error(f"Revert failed: {err}")
            return False
    logger.info(f"Reverted commit {commit_hash}")
    return True

async def get_diff(branch1: str, branch2: str) -> Optional[str]:
    """Get the diff between two branches."""
    code, out, err = await _run(f"git diff {branch1} {branch2}")
    if code != 0:
        logger.error(f"Failed to get diff: {err}")
        return None
    return out

async def get_log(branch: str) -> Optional[str]:
    """Get the commit log for a branch."""
    code, out, err = await _run(f"git log {branch}")
    if code != 0:
        logger.error(f"Failed to get log: {err}")
        return None
    return out

async def get_file_content(path: str) -> Optional[str]:
    """Get the content of a file."""
    code, out, err = await _run(f"git show HEAD:{path}")
    if code != 0:
        logger.error(f"Failed to get file content: {err}")
        return None
    return out

async def write_file(path: str, content: str) -> bool:
    """Write content to a file."""
    with open(path, 'w') as f:
        f.write(content)
    await _run(f'git add "{path}"')
    return True

async def list_files() -> List[str]:
    """List all files in the repository."""
    code, out, err = await _run("git ls-files")
    if code != 0:
        logger.error(f"Failed to list files: {err}")
        return []
    return out.splitlines()