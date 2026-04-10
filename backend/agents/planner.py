import json
import logging
from backend.agents.base import Agent
from backend import db
from backend.services import git_service

logger = logging.getLogger(__name__)


class PlannerAgent(Agent):
    name = "planner"
    model = "qwen2.5:7b"

    async def evaluate_and_propose(self) -> dict:
        """Evaluate the system and propose an improvement.

        Returns a proposal dict with:
            description: str
            files: list[str]
            expected_outcome: str
            risk: str (low/medium/high)
        """
        # Gather context
        feedback_summary = await db.get_feedback_summary()
        recent_cycles = await db.list_cycles(limit=5)
        file_list = await git_service.list_files()
        git_log = await git_service.get_log(10)

        # Read the project's own structure for self-awareness
        codebase_overview = []
        key_files = [
            "backend/orchestrator.py",
            "backend/agents/base.py",
            "backend/main.py",
            "requirements.txt",
        ]
        for f in key_files:
            content = await git_service.get_file_content(f)
            if content:
                codebase_overview.append(f"--- {f} ---\n{content[:2000]}")

        context = f"""## Current System State

### Feedback Summary
- Total thumbs up: {feedback_summary['total_up']}
- Total thumbs down: {feedback_summary['total_down']}

### Recent Negative Feedback (learn from these):
{json.dumps(feedback_summary['recent_negative_feedback'], indent=2)}

### Recent Positive Feedback (keep doing these):
{json.dumps(feedback_summary['recent_positive_feedback'], indent=2)}

### Recent Cycles:
{json.dumps([{{'id': c['id'], 'status': c['status'], 'proposal': c.get('proposal', '')}} for c in recent_cycles], indent=2)}

### Git Log (recent commits):
{git_log}

### Files in Project:
{chr(10).join(file_list[:50])}

### Key File Contents:
{chr(10).join(codebase_overview)}

## Task
Analyze the current state of this project and propose ONE specific improvement.
Focus on:
1. Fixing anything that received thumbs-down feedback
2. Improving code quality, test coverage, or performance
3. Adding missing capabilities
4. Optimizing agent prompts based on feedback patterns

Respond with ONLY a JSON object (no markdown, no explanation):
{{
    "description": "What this change does and why",
    "files": ["list", "of", "files", "to", "modify"],
    "expected_outcome": "What will be better after this change",
    "risk": "low|medium|high"
}}"""

        result = await self.invoke_structured(context)

        # Validate required fields
        required = ["description", "files", "expected_outcome", "risk"]
        for field in required:
            if field not in result or result.get(field) == "":
                result[field] = result.get(field, "unknown")

        if "files" not in result or not isinstance(result.get("files"), list):
            result["files"] = []
        if "risk" not in result or result["risk"] not in ("low", "medium", "high"):
            result["risk"] = "medium"

        return result


planner = PlannerAgent()
