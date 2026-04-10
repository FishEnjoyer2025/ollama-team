import json
import logging
from backend.agents.base import Agent
from backend.services import git_service

logger = logging.getLogger(__name__)


class ReviewerAgent(Agent):
    name = "reviewer"
    model = "qwen2.5-coder:3b"  # 3B is fine for review — faster

    async def review(self, proposal: dict, branch: str) -> dict:
        """Review changes on a branch."""
        diff = await git_service.get_diff(branch)

        if not diff:
            return {
                "approved": False,
                "explanation": "No changes found",
                "issues": ["Empty diff"],
            }

        context = f"""Review this diff for bugs and correctness:

{diff[:3000]}

JSON only: {{"approved": true/false, "explanation": "...", "issues": []}}"""

        result = await self.invoke_structured(context)

        if "approved" not in result:
            result["approved"] = False
        if "explanation" not in result:
            result["explanation"] = result.get("raw_response", "Parse failed")
        if "issues" not in result:
            result["issues"] = []
        result["approved"] = bool(result["approved"])

        return result


reviewer = ReviewerAgent()
