import asyncio
import logging
from backend.agents.base import Agent
from backend.services import git_service

logger = logging.getLogger(__name__)


class TesterAgent(Agent):
    name = "tester"
    model = "qwen2.5-coder:3b"

    async def run_tests(self) -> dict:
        """Run the test suite and return results.

        Returns:
            {"passed": bool, "output": str, "summary": str}
        """
        proc = await asyncio.create_subprocess_shell(
            "python -m pytest tests/ -v --tb=short 2>&1",
            cwd=git_service.REPO_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() + stderr.decode()
        passed = proc.returncode == 0

        return {
            "passed": passed,
            "output": output[-3000:],  # Tail of output
            "summary": "All tests passed" if passed else f"Tests failed (exit code {proc.returncode})",
        }

    async def write_tests(self, proposal: dict, edits: list[dict]) -> list[dict]:
        """Generate tests for the proposed changes.

        Args:
            proposal: The improvement proposal
            edits: The file edits that were made

        Returns:
            List of test file edits: [{"path": str, "content": str}]
        """
        # Read existing tests for style reference
        existing_tests = await git_service.get_file_content("tests/test_orchestrator.py")
        test_style = existing_tests[:1500] if existing_tests else "# No existing tests yet"

        # Build context about what changed
        changes_desc = []
        for edit in edits:
            changes_desc.append(f"File: {edit['path']}\nContent:\n{edit['content'][:1000]}")

        context = f"""## Task
Write pytest tests for the following changes.

**Proposal:** {proposal.get('description', '')}

## Changes Made
{chr(10).join(changes_desc)}

## Existing Test Style
{test_style}

## Instructions
Write focused tests that verify the changes work correctly.
- Use pytest conventions
- Test the happy path and key edge cases
- Keep tests simple and readable
- Don't test protected/unmodified code

Respond with ONLY a JSON array (no markdown):
[
    {{"path": "tests/test_something.py", "content": "complete test file content"}}
]"""

        result = await self.invoke_structured(context)

        if isinstance(result, dict) and "raw_response" in result:
            return []
        if isinstance(result, list):
            return result
        if "path" in result:
            return [result]
        return []

    async def validate(self, proposal: dict, edits: list[dict]) -> dict:
        """Full validation: write tests + run all tests.

        Returns:
            {"passed": bool, "output": str, "summary": str, "new_tests": list}
        """
        # Write new tests for the change
        new_tests = await self.write_tests(proposal, edits)
        for test in new_tests:
            if test.get("path") and test.get("content"):
                await git_service.write_file(test["path"], test["content"])

        # Run full test suite
        results = await self.run_tests()
        results["new_tests"] = [t.get("path", "") for t in new_tests]
        return results


tester = TesterAgent()
