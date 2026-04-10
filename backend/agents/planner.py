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

Modifiable files: backend/agents/planner.py, coder.py, reviewer.py, tester.py, deployer.py, backend/services/ollama_service.py, tools.py, git_service.py, prompts/*.md, tests/*.py

Pick ONE improvement from this list (choose randomly, not always #1):
1. Add a new test to tests/
2. Improve a prompt in prompts/ for clearer instructions
3. Add logging to an agent in backend/agents/
4. Optimize ollama_service.py settings
5. Improve git_service.py with better error handling
6. Add input validation to an agent

JSON only:
{{"description": "...", "files": ["max 2 files"], "expected_outcome": "...", "risk": "low"}}"""

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
