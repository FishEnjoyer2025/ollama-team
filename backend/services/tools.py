"""Tools that agents can use to validate and test their work."""
import asyncio
import ast
import logging
from pathlib import Path
from backend.services import git_service

logger = logging.getLogger(__name__)


async def validate_python_syntax(file_path: str) -> tuple[bool, str]:
    """Check if a Python file has valid syntax. Returns (valid, error_msg)."""
    full_path = git_service.REPO_PATH / file_path
    if not full_path.exists():
        return False, f"File not found: {file_path}"
    if not file_path.endswith(".py"):
        return True, "Not a Python file, skipping"
    try:
        source = full_path.read_text(encoding="utf-8")
        ast.parse(source)
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"


async def lint_file(file_path: str) -> tuple[bool, str]:
    """Run ruff on a file. Returns (clean, output)."""
    full_path = git_service.REPO_PATH / file_path
    if not full_path.exists() or not file_path.endswith(".py"):
        return True, "Skipped"
    proc = await asyncio.create_subprocess_shell(
        f'ruff check "{full_path}" --select E,F --no-fix',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode().strip()
    clean = proc.returncode == 0
    return clean, output if output else "Clean"


async def try_import(module_path: str) -> tuple[bool, str]:
    """Try to import a Python module to check for import errors.
    module_path is like 'backend/agents/coder.py' -> 'backend.agents.coder'
    """
    if not module_path.endswith(".py"):
        return True, "Not a Python file"
    module_name = module_path.replace("/", ".").replace("\\", ".").removesuffix(".py")
    proc = await asyncio.create_subprocess_shell(
        f'python -c "import {module_name}"',
        cwd=git_service.REPO_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        return True, "Import OK"
    return False, stderr.decode().strip()[-500:]


async def run_command(cmd: str, timeout: float = 30.0) -> tuple[int, str]:
    """Run a shell command in the repo directory. Returns (exit_code, output)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=git_service.REPO_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode() + stderr.decode()
        return proc.returncode, output[-2000:]
    except asyncio.TimeoutError:
        proc.kill()
        return -1, f"Command timed out after {timeout}s"


async def validate_edits(edits: list[dict]) -> tuple[bool, list[str]]:
    """Validate all file edits before committing.
    Returns (all_valid, list_of_issues).
    """
    issues = []
    for edit in edits:
        path = edit.get("path", "")
        if not path.endswith(".py"):
            continue

        # Syntax check
        valid, msg = await validate_python_syntax(path)
        if not valid:
            issues.append(f"{path}: {msg}")
            continue

        # Lint check
        clean, lint_output = await lint_file(path)
        if not clean:
            # Lint warnings are non-blocking but logged
            logger.warning(f"Lint issues in {path}: {lint_output}")

    return len(issues) == 0, issues
