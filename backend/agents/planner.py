import json
import logging
from backend.agents.base import Agent
from backend import db
from backend.services import git_service

logger = logging.getLogger(__name__)


class PlannerAgent(Agent):
    name = "planner"
    model = "qwen2.5-coder:7b"

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

        context = f"""You are the Planner for Ollama Team — a self-improving AI system with a React dashboard.
Your job: propose ONE creative improvement that makes the system cooler, more useful, or more fun.

Feedback: {feedback_summary['total_up']} thumbs up, {feedback_summary['total_down']} thumbs down
{guidance_block}
Recent cycles (DO NOT repeat these):
{chr(10).join(cycle_info) if cycle_info else "None yet — first cycle! Do something fun."}

WHAT YOU CAN MODIFY (max 2 files per proposal):
- frontend/src/pages/*.tsx — Dashboard pages (React + TailwindCSS)
- frontend/src/components/*.tsx — UI components (create new ones!)
- backend/agents/*.py — Agent implementations (improve yourself!)
- backend/services/*.py — Services (llm_service, git_service, tools, health)
- prompts/*.md — Agent system prompts
- tests/test_*.py — Test files

WHAT YOU CANNOT MODIFY (will be blocked):
- backend/main.py, orchestrator.py, db.py (core loop — touching these bricks the system)
- frontend/src/App.tsx, api.ts, main.tsx, hooks/ (core frontend wiring)

YOUR ONLY OBJECTIVE: Make the agents SMARTER and FASTER. Every cycle should improve speed or intelligence.

IDEAS (pick one, or invent your own):
- Optimize prompts to get better output with fewer tokens
- Add caching to avoid redundant work (file reads, model calls)
- Make the coder's output parsing more robust and faster
- Improve the reviewer to catch more real bugs, fewer false positives
- Make the tester smarter about what to test
- Reduce latency in the pipeline (fewer round trips, smarter retries)
- Improve JSON/code extraction from model output
- Add smarter context selection — feed agents only what they need
- Optimize the planner to make better proposals based on feedback patterns
- Improve error recovery — fail fast, retry smart

Output ONLY this JSON (no other text):
{{"description": "what you want to do", "files": ["path/to/file1.tsx"], "expected_outcome": "what it achieves", "risk": "low"}}"""

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
