import asyncio
import logging
from backend.agents.base import Agent
from backend.services import git_service

logger = logging.getLogger(__name__)


class TesterAgent(Agent):
    name = "tester"
    model = "qwen2.5-coder:7b"

    async def run_tests(self) -> dict:
        """Run the test suite. Returns {"passed": bool, "output": str, "summary": str}."""
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
            "output": output[-2000:],
            "summary": "All tests passed" if passed else f"Tests failed (exit {proc.returncode})",
        }

    async def validate(self, proposal: dict, edits: list[dict]) -> dict:
        """Just run existing tests — skip LLM test generation for speed."""
        results = await self.run_tests()
        results["new_tests"] = []
        return results


tester = TesterAgent()
