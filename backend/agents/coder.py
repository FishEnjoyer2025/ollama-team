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

        Returns:
            List of file edits: [{"path": str, "content": str}]
        """
        # Limit to 2 files max to keep generation fast
        target_files = proposal.get("files", [])[:2]

        # Read only the target files (no extra context — speed over quality)
        file_contents = {}
        for f in target_files:
            content = await git_service.get_file_content(f)
            if content is not None:
                # Truncate large files to keep prompt small
                file_contents[f] = content[:2000]

        context = f"""Modify these files for: {proposal.get('description', '')}

{chr(10).join(f'--- {path} ---{chr(10)}{content}' for path, content in file_contents.items())}

Output ONLY a JSON array. Each item has "path" and "content" (the full new file).
Keep changes minimal. Output:"""

        result = await self.invoke_structured(context)

        if isinstance(result, dict) and "raw_response" in result:
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

        if isinstance(result, dict) and "path" in result and "content" in result:
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
