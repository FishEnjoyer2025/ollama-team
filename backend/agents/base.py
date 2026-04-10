import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from backend.services.llm_service import llm
from backend import db

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


class Agent:
    """Base agent class. Each agent has a name, model, and system prompt."""

    name: str = "base"
    model: str = "qwen2.5-coder:7b"
    default_timeout: float = 600.0  # 10 minutes (CPU inference is slow)

    def __init__(self):
        self._prompt_cache: Optional[str] = None

    @property
    def prompt_path(self) -> Path:
        return PROMPTS_DIR / f"{self.name}.md"

    def load_prompt(self) -> str:
        """Load the system prompt from disk (always fresh, prompts may evolve)."""
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        logger.warning(f"No prompt file found for {self.name} at {self.prompt_path}")
        return f"You are the {self.name} agent."

    async def invoke(self, context: str, timeout: Optional[float] = None, json_mode: bool = False) -> str:
        """Invoke this agent with context. Returns the response text."""
        timeout = timeout or self.default_timeout
        system_prompt = self.load_prompt()

        start = time.monotonic()
        success = False
        try:
            response = await asyncio.wait_for(
                llm.generate(
                    model=self.model,
                    prompt=context,
                    system=system_prompt,
                    timeout=timeout,
                    json_mode=json_mode,
                ),
                timeout=timeout + 10,
            )
            success = True
            return response
        except asyncio.TimeoutError:
            logger.error(f"Agent {self.name} timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            raise
        finally:
            duration = time.monotonic() - start
            await db.record_agent_invocation(self.name, success, duration)

    async def invoke_json(self, context: str, timeout: Optional[float] = None) -> str:
        """Invoke with Ollama's JSON mode forced — guarantees valid JSON output."""
        return await self.invoke(context, timeout, json_mode=True)

    async def invoke_structured(
        self, context: str, timeout: Optional[float] = None
    ) -> dict:
        """Invoke with JSON mode and parse the response."""
        raw = await self.invoke_json(context, timeout)
        return self._parse_json(raw)

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from agent response. Handles markdown code blocks."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if "```json" in text:
            try:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Try extracting from generic code block
        if "```" in text:
            try:
                start = text.index("```") + 3
                newline = text.index("\n", start)
                end = text.index("```", newline)
                return json.loads(text[newline:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Try finding JSON object in text
        for i, ch in enumerate(text):
            if ch == "{":
                depth = 0
                for j in range(i, len(text)):
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[i : j + 1])
                            except json.JSONDecodeError:
                                break
                break

        # Fallback
        logger.warning(f"Could not parse JSON from {self.name} response, wrapping raw text")
        return {"raw_response": text}
