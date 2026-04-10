import json
import logging
from backend.agents.base import Agent
from backend.services import git_service

logger = logging.getLogger(__name__)


class ReviewerAgent(Agent):
    name = "reviewer"
    model = "qwen2.5-coder:7b"

    async def review(self, proposal: dict, branch: str) -> dict:
        """Review changes on a branch.

        Returns:
            {"approved": bool, "explanation": str, "issues": list[str]}
        """
        diff = await git_service.get_diff(branch)

        if not diff:
            return {
                "approved": False,
                "explanation": "No changes found on branch",
                "issues": ["Empty diff — coder may have failed to write files"],
            }

        context = f"""## Task
Review the following code changes for quality and correctness.

**Proposal:** {proposal.get('description', '')}
**Expected Outcome:** {proposal.get('expected_outcome', '')}
**Risk Level:** {proposal.get('risk', 'medium')}

## Diff
```
{diff[:6000]}
```

## Review Criteria
1. **Correctness** — Does the code do what the proposal describes?
2. **Bugs** — Any logic errors, off-by-one, null references, race conditions?
3. **Security** — Any injection, path traversal, or unsafe operations?
4. **Style** — Does it follow existing code conventions?
5. **Completeness** — Are all proposed changes implemented? Anything missing?
6. **Protected files** — Does it modify any files it shouldn't? (db.py schema, health.py, .gitignore, frontend/)

Respond with ONLY a JSON object (no markdown, no explanation):
{{
    "approved": true/false,
    "explanation": "Brief summary of your assessment",
    "issues": ["list of specific issues found, empty if approved"]
}}"""

        result = await self.invoke_structured(context)

        # Normalize
        if "approved" not in result:
            result["approved"] = False
        if "explanation" not in result:
            result["explanation"] = result.get("raw_response", "Review failed to parse")
        if "issues" not in result:
            result["issues"] = []

        # Ensure approved is actually a bool
        result["approved"] = bool(result["approved"])

        return result


reviewer = ReviewerAgent()
