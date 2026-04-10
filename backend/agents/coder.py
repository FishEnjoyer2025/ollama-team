import json
import logging
from backend.agents.base import Agent
from backend.services import git_service

logger = logging.getLogger(__name__)

PROJECT_STRUCTURE = """Project layout and API reference:

BACKEND (Python, FastAPI):
- backend/agents/base.py: Agent base class with invoke(), invoke_json(), invoke_structured()
- backend/agents/planner.py, coder.py, reviewer.py, tester.py, deployer.py
- backend/services/git_service.py: create_branch(), checkout(), commit(), merge(), get_diff(), get_file_content(path), write_file(path, content), list_files()
- backend/services/tools.py: validate_python_syntax(path), lint_file(path), validate_edits(edits), run_command(cmd)
- Tests: from backend.agents.reviewer import reviewer (lowercase singleton)
- Prompts: plain markdown files in prompts/

FRONTEND (React 19 + TypeScript + TailwindCSS + Vite):
- frontend/src/App.tsx: Main router with tabs: Activity, Cycles, Agents, Health, Settings
- frontend/src/api.ts: API client — getCycles(), getAgents(), getSystemHealth(), submitFeedback(), etc.
- frontend/src/hooks/useWebSocket.ts: Real-time WebSocket connection
- frontend/src/pages/ActivityFeed.tsx: Live activity, guidance box, status banner
- frontend/src/pages/CycleHistory.tsx: Completed cycles with expandable details + feedback buttons
- frontend/src/pages/AgentProfiles.tsx: Per-agent stats and prompt viewer
- frontend/src/pages/SystemHealth.tsx: System resource monitoring
- frontend/src/pages/Settings.tsx: Configuration panel
- frontend/src/components/*.tsx: Reusable UI components (create new ones here!)

API BASE: http://localhost:8000 — All endpoints under /api/
Key endpoints: GET /api/cycles, GET /api/agents, GET /api/system/health, POST /api/cycles/{id}/feedback

STYLE: Dark theme (bg-gray-900/800), accent colors per agent (purple=planner, blue=coder, yellow=reviewer, green=tester, orange=deployer). Use TailwindCSS classes. Keep it fun and visual."""


class CoderAgent(Agent):
    name = "coder"
    model = "qwen2.5-coder:7b"

    async def implement(self, proposal: dict) -> list[dict]:
        """Implement one file at a time for reliability."""
        target_files = proposal.get("files", [])[:2]
        retry_error = proposal.get("_retry_error", "")
        edits = []

        for filepath in target_files:
            current = await git_service.get_file_content(filepath)
            edit = await self._implement_single_file(
                filepath, current, proposal.get("description", ""), retry_error,
            )
            if edit:
                edits.append(edit)

        return edits

    async def _implement_single_file(self, filepath: str, current_content: str | None, task: str, retry_error: str = "") -> dict | None:
        """Generate the new content for a single file."""
        current_block = ""
        if current_content:
            current_block = f"Current content of {filepath}:\n{current_content[:2500]}"
        else:
            current_block = f"{filepath} does not exist yet. Create it."

        # Show context depending on file type
        template_block = ""
        if filepath.startswith("tests/"):
            existing = await git_service.get_file_content("tests/test_agents.py")
            if existing:
                template_block = f"\nExample test file (follow this style):\n{existing[:1500]}\n"
            test_name = filepath.replace("tests/test_", "").replace(".py", "")
            for candidate in [f"backend/services/{test_name}.py", f"backend/agents/{test_name}.py", f"backend/{test_name}.py"]:
                source = await git_service.get_file_content(candidate)
                if source:
                    template_block += f"\nSource code of {candidate} (import from here, use these exact function names):\n{source[:3000]}\n"
                    break
        elif filepath.startswith("frontend/"):
            # Show an existing page as reference for style/patterns
            ref = await git_service.get_file_content("frontend/src/pages/ActivityFeed.tsx")
            if ref:
                template_block = f"\nReference page (follow this React + TailwindCSS style):\n{ref[:2500]}\n"
            # Show api.ts so the coder knows available API functions
            api = await git_service.get_file_content("frontend/src/api.ts")
            if api:
                template_block += f"\nAvailable API functions (frontend/src/api.ts):\n{api[:2000]}\n"

        error_block = ""
        if retry_error:
            error_block = f"\nPREVIOUS ATTEMPT FAILED: {retry_error}\nFix the issue this time.\n"

        context = f"""{PROJECT_STRUCTURE}

{current_block}
{template_block}{error_block}
Task: {task}

Write the COMPLETE file content for {filepath} inside a markdown code block like this:
```python
# your code here
```
Do NOT use JSON. Just write the Python code inside the code block."""

        raw = await self.invoke(context)

        # Extract code from markdown code block
        content = self._extract_code_block(raw)
        if content:
            return {"path": filepath, "content": content}

        logger.error(f"Could not parse coder output for {filepath}")
        return None

    def _extract_code_block(self, text: str) -> str | None:
        """Extract code from markdown code blocks."""
        # Try ```python ... ```
        for marker in ["```python", "```py", "```"]:
            if marker in text:
                try:
                    start = text.index(marker) + len(marker)
                    # Skip to next line
                    if text[start] == "\n":
                        start += 1
                    end = text.index("```", start)
                    code = text[start:end].strip()
                    if len(code) > 10:
                        return code
                except (ValueError, IndexError):
                    continue
        # Fallback: if it looks like raw Python code (starts with import/from/def/class)
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ", "def ", "class ", "#")):
                # Take everything from this line onward
                idx = text.index(line)
                code = text[idx:].strip()
                if len(code) > 10:
                    return code
        return None

    async def apply_edits(self, edits: list[dict], allowed_paths: list[str] = None) -> list[str]:
        """Write file edits to disk. Returns list of modified file paths."""
        modified = []
        for edit in edits:
            path = edit.get("path", "")
            content = edit.get("content", "")
            if not path or not content:
                continue
            # Safety: path must have a file extension (not a bare directory)
            if "." not in path.split("/")[-1]:
                logger.warning(f"Coder output a directory path '{path}' instead of a file — blocked")
                continue
            # Safety: only write to files that were in the proposal
            if allowed_paths and path not in allowed_paths:
                logger.warning(f"Coder tried to write to {path} which wasn't in the proposal — blocked")
                continue
            # Safety: content must be at least 10 chars (prevent blank overwrites)
            if len(content.strip()) < 10:
                logger.warning(f"Coder produced near-empty content for {path} — blocked")
                continue
            await git_service.write_file(path, content)
            modified.append(path)
            logger.info(f"Wrote: {path}")
        return modified


coder = CoderAgent()
