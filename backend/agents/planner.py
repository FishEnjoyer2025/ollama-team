import json
import logging
from backend.agents.base import Agent
from backend import db
from backend.services import git_service

logger = logging.getLogger(__name__)


class PlannerAgent(Agent):
    name = "planner"
    model = "qwen2.5-coder:3b"

    async def evaluate_and_propose(self) -> dict:
        """Evaluate the system and propose an improvement."""
        feedback_summary = await db.get_feedback_summary()
        recent_cycles = await db.list_cycles(limit=3)
        file_list = await git_service.list_files()
        settings = await db.get_settings()
        guidance = settings.get("guidance", "")

        cycle_info = []
        for c in recent_cycles:
            p = c.get("proposal", "")
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except (json.JSONDecodeError, TypeError):
                    pass
            desc = p.get("description", "") if isinstance(p, dict) else str(p)[:80]
            cycle_info.append(f"- {c['id']} {c['status']}: {desc[:80]}")

        guidance_block = ""
        if guidance:
            guidance_block = f"\nOPERATOR GUIDANCE (highest priority):\n{guidance}\n"

        context = f"""Thumbs up: {feedback_summary['total_up']} | Thumbs down: {feedback_summary['total_down']}
{guidance_block}
Recent cycles (DO NOT repeat these — pick something DIFFERENT):
{chr(10).join(cycle_info) if cycle_info else "None yet"}

Pick ONE task. Use EXACT file paths (not directories or globs):
1. {{"description": "Add test for reviewer", "files": ["tests/test_reviewer.py"], "expected_outcome": "Better test coverage", "risk": "low"}}
2. {{"description": "Improve reviewer prompt", "files": ["prompts/reviewer.md"], "expected_outcome": "Better reviews", "risk": "low"}}
3. {{"description": "Add logging to deployer", "files": ["backend/agents/deployer.py"], "expected_outcome": "Better visibility", "risk": "low"}}
4. {{"description": "Improve git_service error handling", "files": ["backend/services/git_service.py"], "expected_outcome": "Graceful failures", "risk": "low"}}
5. {{"description": "Add test for git_service", "files": ["tests/test_git_service.py"], "expected_outcome": "Better coverage", "risk": "low"}}
6. {{"description": "Improve tester prompt", "files": ["prompts/tester.md"], "expected_outcome": "Better testing", "risk": "low"}}

Output ONE of these JSON objects (or similar). Vary your choice each cycle:"""

        result = await self.invoke_structured(context)

        if "files" not in result or not isinstance(result.get("files"), list):
            result["files"] = []
        result["files"] = result["files"][:2]
        if "risk" not in result or result["risk"] not in ("low", "medium", "high"):
            result["risk"] = "low"
        for field in ["description", "expected_outcome"]:
            if field not in result:
                result[field] = "unknown"

        return result


planner = PlannerAgent()
