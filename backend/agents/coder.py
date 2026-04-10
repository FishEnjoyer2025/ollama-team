import json
import logging
from backend.agents.base import Agent
from backend.services import git_service

logger = logging.getLogger(__name__)


class CoderAgent(Agent):
    name = "coder"
    model = "qwen2.5-coder:7b"

    async def implement(self, proposal: dict) -> list[dict]:
        """Implement a proposed change.

        Args:
            proposal: dict with description, files, expected_outcome, risk

        Returns:
            List of file edits: [{"path": str, "content": str}]
        """
        # Read current content of files to modify
        file_contents = {}
        for f in proposal.get("files", []):
            content = await git_service.get_file_content(f)
            if content is not None:
                file_contents[f] = content

        # Also read related files for context
        all_files = await git_service.list_files()
        related = [f for f in all_files if any(
            f.startswith(p.rsplit("/", 1)[0] + "/") if "/" in p else False
            for p in proposal.get("files", [])
        )]
        for f in related[:5]:  # Limit context
            if f not in file_contents:
                content = await git_service.get_file_content(f)
                if content:
                    file_contents[f] = content[:1500]  # Truncate for context

        context = f"""## Task
Implement the following improvement to this codebase:

**Description:** {proposal.get('description', '')}
**Expected Outcome:** {proposal.get('expected_outcome', '')}
**Risk Level:** {proposal.get('risk', 'medium')}

## Files to Modify
{json.dumps(proposal.get('files', []))}

## Current File Contents
{chr(10).join(f'--- {path} ---{chr(10)}{content}' for path, content in file_contents.items())}

## Instructions
Implement the change. For each file you modify or create, output the COMPLETE new file content.

Respond with ONLY a JSON array (no markdown, no explanation):
[
    {{"path": "relative/path/to/file.py", "content": "complete file content here"}},
    ...
]

Rules:
- Output the COMPLETE file content, not patches or diffs
- Only modify files listed in the proposal, unless you need to create a new file
- Follow existing code style and conventions
- Do not modify protected files (backend/services/health.py, backend/db.py schema)
- Include proper imports
- Keep changes minimal and focused"""

        result = await self.invoke_structured(context)

        # Handle response format
        if isinstance(result, dict) and "raw_response" in result:
            # Try to parse as a list from raw response
            raw = result["raw_response"]
            try:
                if "[" in raw:
                    start = raw.index("[")
                    end = raw.rindex("]") + 1
                    return json.loads(raw[start:end])
            except (ValueError, json.JSONDecodeError):
                pass
            logger.error("Coder produced unparseable output")
            return []

        if isinstance(result, list):
            return result

        # Single file edit wrapped in dict
        if "path" in result and "content" in result:
            return [result]

        return []

    async def apply_edits(self, edits: list[dict]) -> list[str]:
        """Write file edits to disk. Returns list of modified file paths."""
        modified = []
        for edit in edits:
            path = edit.get("path", "")
            content = edit.get("content", "")
            if not path or not content:
                continue
            await git_service.write_file(path, content)
            modified.append(path)
            logger.info(f"Wrote: {path}")
        return modified


coder = CoderAgent()
