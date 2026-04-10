import asyncio
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"


class OllamaService:
    def __init__(self):
        self.current_model: Optional[str] = None

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        timeout: float = 300.0,
    ) -> str:
        """Generate a response from Ollama. Loads model if not already loaded."""
        if self.current_model != model:
            await self.load_model(model)

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{OLLAMA_BASE}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "system": system,
                        "stream": False,
                        "options": {
                            "num_ctx": 8192,
                            "temperature": 0.7,
                        },
                    },
                    timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")
            except httpx.TimeoutException:
                logger.error(f"Ollama generate timed out after {timeout}s for model {model}")
                raise
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")
                raise

    async def chat(
        self,
        model: str,
        messages: list[dict],
        timeout: float = 300.0,
    ) -> str:
        """Chat-style generation with message history."""
        if self.current_model != model:
            await self.load_model(model)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_ctx": 8192,
                        "temperature": 0.7,
                    },
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    async def load_model(self, model: str):
        """Pre-load a model into memory. Unloads current model first."""
        if self.current_model and self.current_model != model:
            await self.unload_model(self.current_model)

        logger.info(f"Loading model: {model}")
        async with httpx.AsyncClient() as client:
            # Sending a blank generate pre-loads the model
            try:
                await client.post(
                    f"{OLLAMA_BASE}/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": "10m"},
                    timeout=120.0,
                )
                self.current_model = model
                logger.info(f"Model loaded: {model}")
            except Exception as e:
                logger.error(f"Failed to load model {model}: {e}")
                raise

    async def unload_model(self, model: str):
        """Unload a model from memory."""
        logger.info(f"Unloading model: {model}")
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{OLLAMA_BASE}/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": "0"},
                    timeout=30.0,
                )
                if self.current_model == model:
                    self.current_model = None
            except Exception as e:
                logger.warning(f"Failed to unload model {model}: {e}")

    async def list_models(self) -> list[dict]:
        """List all available models."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{OLLAMA_BASE}/api/tags", timeout=10.0)
                resp.raise_for_status()
                return resp.json().get("models", [])
            except Exception as e:
                logger.error(f"Failed to list models: {e}")
                return []

    async def get_status(self) -> dict:
        """Check if Ollama is running and what's loaded."""
        try:
            models = await self.list_models()
            return {
                "online": True,
                "models": [m["name"] for m in models],
                "current_model": self.current_model,
            }
        except Exception:
            return {
                "online": False,
                "models": [],
                "current_model": None,
            }

    async def pull_model(self, model: str) -> bool:
        """Pull a model from the Ollama registry."""
        logger.info(f"Pulling model: {model}")
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{OLLAMA_BASE}/api/pull",
                    json={"name": model, "stream": False},
                    timeout=600.0,  # Models can be large
                )
                resp.raise_for_status()
                logger.info(f"Model pulled: {model}")
                return True
            except Exception as e:
                logger.error(f"Failed to pull model {model}: {e}")
                return False


# Singleton
ollama = OllamaService()
