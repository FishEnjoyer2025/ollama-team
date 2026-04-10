import json
import logging
from backend.agents.base import Agent
from backend.services import git_service

logger = logging.getLogger(__name__)

PROJECT_STRUCTURE = """Project layout (use these import paths):
- backend/agents/planner.py, coder.py, reviewer.py, tester.py, deployer.py
- backend/services/ollama_service.py, git_service.py, tools.py
- backend/agents/base.py (DO NOT MODIFY - protected)
- tests/test_*.py (imports: from backend.agents.planner import planner)
- prompts/*.md (agent system prompts, plain markdown)"""


class CoderAgent(Agent):
    name = "coder"
    model = "qwen2.5-coder:7b"

    async def implement(self, proposal: dict) -> list[dict]:
        """Implement one file at a time for reliability."""
        target_files = proposal.get("files", [])[:2]
        edits = []

        for filepath in target_files:
            current = await git_service.get_file_content(filepath)
            edit = await self._implement_single_file(
                filepath,
                current,
                proposal.get("description", ""),
            )
            if edit:
                edits.append(edit)

        return edits

    async def _implement_single_file(self, filepath: str, current_content: str | None, task: str) -> dict | None:
        """Generate the new content for a single file."""
        current_block = ""
        if current_content:
            current_block = f"Current content of {filepath}:\n{current_content[:2500]}"
        else:
            current_block = f"{filepath} does not exist yet. Create it."

        context = f"""{PROJECT_STRUCTURE}

{current_block}

Task: {task}

Respond with JSON: {{"path": "{filepath}", "content": "the complete new file content"}}"""

        raw = await self.invoke_json(context)

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "content" in parsed:
                return {"path": filepath, "content": parsed["content"]}
            if isinstance(parsed, list) and parsed:
                item = parsed[0]
                if isinstance(item, dict) and "content" in item:
                    return {"path": filepath, "content": item["content"]}
        except json.JSONDecodeError:
            pass

        # Try extracting from raw text
        try:
            for opener in ["{", "["]:
                if opener in raw:
                    start = raw.index(opener)
                    parsed = json.loads(raw[start:])
                    if isinstance(parsed, dict) and "content" in parsed:
                        return {"path": filepath, "content": parsed["content"]}
                    if isinstance(parsed, list) and parsed and "content" in parsed[0]:
                        return {"path": filepath, "content": parsed[0]["content"]}
        except (json.JSONDecodeError, ValueError, IndexError):
            pass

        logger.error(f"Could not parse coder output for {filepath}")
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
