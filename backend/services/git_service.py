import asyncio
import logging
from pathlib import Path
from typing import Optional

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


async def commit(message: str, files: Optional[list[str]] = None) -> Optional[str]:
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
    target = commit_hash or "HEAD"
    code, out, err = await _run(f"git revert {target} --no-edit")
    if code != 0:
        logger.error(f"Revert failed: {err}")
        await _run("git revert --abort")
        return False
    logger.info(f"Reverted {target}")
    return True


async def get_diff(branch: Optional[str] = None) -> str:
    """Get the diff of current changes or between branches."""
    if branch:
        code, out, err = await _run(f"git diff main...{branch}")
    else:
        code, out, err = await _run("git diff")
    return out


async def get_staged_diff() -> str:
    """Get the diff of staged changes."""
    code, out, err = await _run("git diff --cached")
    return out


async def get_log(count: int = 10) -> str:
    """Get recent commit log."""
    code, out, err = await _run(f"git log --oneline -n {count}")
    return out


async def delete_branch(name: str) -> bool:
    """Delete a branch (must not be currently checked out)."""
    code, out, err = await _run(f"git branch -D {name}")
    return code == 0


async def get_file_content(path: str) -> Optional[str]:
    """Read a file from the repo."""
    full_path = REPO_PATH / path
    if not full_path.exists():
        return None
    return full_path.read_text(encoding="utf-8")


async def write_file(path: str, content: str):
    """Write content to a file in the repo."""
    full_path = REPO_PATH / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")


async def list_files(directory: str = ".") -> list[str]:
    """List tracked files in a directory."""
    code, out, err = await _run(f"git ls-files {directory}")
    if code != 0:
        return []
    return [f for f in out.split("\n") if f]


async def has_uncommitted_changes() -> bool:
    """Check if there are uncommitted changes."""
    code, out, err = await _run("git status --porcelain")
    return bool(out)
