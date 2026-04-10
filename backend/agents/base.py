import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from backend.services.ollama_service import ollama
from backend import db

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


class Agent:
    """Base agent class. Each agent has a name, model, and system prompt."""

    name: str = "base"
    model: str = "qwen2.5-coder:7b"
    default_timeout: float = 300.0  # 5 minutes

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

    async def invoke(self, context: str, timeout: Optional[float] = None) -> str:
        """Invoke this agent with context. Returns the response text."""
        timeout = timeout or self.default_timeout
        system_prompt = self.load_prompt()

        start = time.monotonic()
        success = False
        try:
            response = await asyncio.wait_for(
                ollama.generate(
                    model=self.model,
                    prompt=context,
                    system=system_prompt,
                    timeout=timeout,
                ),
                timeout=timeout + 10,  # Small buffer over Ollama's timeout
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

    async def invoke_structured(
        self, context: str, timeout: Optional[float] = None
    ) -> dict:
        """Invoke and parse JSON from the response.

        Attempts to extract a JSON object from the response text.
        Falls back to wrapping the raw text in a dict.
        """
        raw = await self.invoke(context, timeout)
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
            start = text.index("```json") + 7
            end = text.index("```", start)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Try extracting from generic code block
        if "```" in text:
            start = text.index("```") + 3
            # Skip language identifier on first line
            newline = text.index("\n", start)
            end = text.index("```", newline)
            try:
                return json.loads(text[newline:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Try finding JSON object in text
        for i, ch in enumerate(text):
            if ch == "{":
                # Find matching closing brace
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
