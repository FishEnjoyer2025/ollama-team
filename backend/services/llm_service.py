"""
LLM inference service — no Ollama dependency.

Uses llama-cpp-python for CPU (home machine) or vLLM for GPU (rental).
Auto-detects which backend is available.

The rest of the codebase talks to this through the same interface
that ollama_service.py used — drop-in replacement.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Model file paths — set via env var or config
MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path.home() / "models"))
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "qwen2.5-coder-7b-q4_k_m.gguf")

# Backend: "llama_cpp" (CPU), "vllm" (GPU), "ollama" (fallback)
BACKEND = os.environ.get("LLM_BACKEND", "auto")

# Generation defaults
DEFAULT_CTX = int(os.environ.get("LLM_CTX", "4096"))
DEFAULT_THREADS = int(os.environ.get("LLM_THREADS", "8"))
DEFAULT_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
DEFAULT_GPU_LAYERS = int(os.environ.get("LLM_GPU_LAYERS", "0"))  # 0 = CPU only, -1 = all GPU


class LLMService:
    """Unified LLM interface. Supports llama.cpp, vLLM, and Ollama fallback."""

    def __init__(self):
        self.backend: Optional[str] = None
        self._llama_model = None
        self._vllm_model = None
        self._initialized = False

    async def initialize(self):
        """Auto-detect and initialize the best available backend."""
        if self._initialized:
            return

        backend = BACKEND

        if backend == "auto":
            # Try vLLM first (GPU), then llama.cpp (CPU), then Ollama (fallback)
            if self._try_vllm():
                backend = "vllm"
            elif self._try_llama_cpp():
                backend = "llama_cpp"
            elif await self._try_ollama():
                backend = "ollama"
            else:
                raise RuntimeError("No LLM backend available. Install llama-cpp-python or set up Ollama.")
        elif backend == "llama_cpp":
            if not self._try_llama_cpp():
                raise RuntimeError("llama-cpp-python not available")
        elif backend == "vllm":
            if not self._try_vllm():
                raise RuntimeError("vLLM not available")
        elif backend == "ollama":
            if not await self._try_ollama():
                raise RuntimeError("Ollama not available")

        self.backend = backend
        self._initialized = True
        logger.info(f"LLM backend: {self.backend}")

    def _try_llama_cpp(self) -> bool:
        """Try to initialize llama-cpp-python."""
        try:
            from llama_cpp import Llama

            model_path = MODEL_DIR / DEFAULT_MODEL
            if not model_path.exists():
                # Check if any .gguf file exists in model dir
                gguf_files = list(MODEL_DIR.glob("*.gguf"))
                if not gguf_files:
                    logger.warning(f"No GGUF model found in {MODEL_DIR}")
                    return False
                model_path = gguf_files[0]
                logger.info(f"Using model: {model_path.name}")

            logger.info(f"Loading llama.cpp model: {model_path}")
            self._llama_model = Llama(
                model_path=str(model_path),
                n_ctx=DEFAULT_CTX,
                n_threads=DEFAULT_THREADS,
                n_gpu_layers=DEFAULT_GPU_LAYERS,
                verbose=False,
            )
            logger.info("llama.cpp model loaded")
            return True
        except ImportError:
            logger.debug("llama-cpp-python not installed")
            return False
        except Exception as e:
            logger.warning(f"llama.cpp init failed: {e}")
            return False

    def _try_vllm(self) -> bool:
        """Try to initialize vLLM (GPU only)."""
        try:
            import torch
            if not torch.cuda.is_available():
                return False

            from vllm import LLM
            model_name = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct")
            logger.info(f"Loading vLLM model: {model_name}")
            self._vllm_model = LLM(
                model=model_name,
                tensor_parallel_size=1,
                max_model_len=DEFAULT_CTX,
                gpu_memory_utilization=0.9,
            )
            logger.info("vLLM model loaded")
            return True
        except ImportError:
            logger.debug("vLLM not installed")
            return False
        except Exception as e:
            logger.warning(f"vLLM init failed: {e}")
            return False

    async def _try_ollama(self) -> bool:
        """Check if Ollama is running as fallback."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:11434/api/tags", timeout=5)
                return resp.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        model: str = "",
        prompt: str = "",
        system: str = "",
        timeout: float = 600.0,
        json_mode: bool = False,
    ) -> str:
        """Generate a response. Model param is used for Ollama fallback."""
        await self.initialize()

        if self.backend == "llama_cpp":
            return await self._generate_llama_cpp(prompt, system, json_mode)
        elif self.backend == "vllm":
            return await self._generate_vllm(prompt, system, json_mode)
        elif self.backend == "ollama":
            return await self._generate_ollama(model, prompt, system, timeout, json_mode)

        raise RuntimeError(f"Unknown backend: {self.backend}")

    async def _generate_llama_cpp(self, prompt: str, system: str, json_mode: bool) -> str:
        """Generate with llama.cpp (runs in thread pool to avoid blocking)."""
        loop = asyncio.get_event_loop()

        def _generate():
            full_prompt = f"{system}\n\n{prompt}" if system else prompt

            kwargs = {
                "prompt": full_prompt,
                "max_tokens": 2048,
                "temperature": DEFAULT_TEMPERATURE,
                "stop": ["```\n\n", "\n\n\n"],
            }

            if json_mode:
                # Force JSON output via grammar
                from llama_cpp import LlamaGrammar
                try:
                    json_grammar = LlamaGrammar.from_string(
                        'root ::= "{" [^}]* "}" | "[" [^\\]]* "]"'
                    )
                    kwargs["grammar"] = json_grammar
                except Exception:
                    # Grammar parsing failed, just let it generate freely
                    pass

            result = self._llama_model(**kwargs)
            return result["choices"][0]["text"]

        return await loop.run_in_executor(None, _generate)

    async def _generate_vllm(self, prompt: str, system: str, json_mode: bool) -> str:
        """Generate with vLLM."""
        from vllm import SamplingParams
        loop = asyncio.get_event_loop()

        def _generate():
            full_prompt = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

            params = SamplingParams(
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=2048,
            )
            if json_mode:
                params.guided_json = True

            outputs = self._vllm_model.generate([full_prompt], params)
            return outputs[0].outputs[0].text

        return await loop.run_in_executor(None, _generate)

    async def _generate_ollama(self, model: str, prompt: str, system: str, timeout: float, json_mode: bool) -> str:
        """Fallback to Ollama HTTP API."""
        import httpx
        payload = {
            "model": model or "qwen2.5-coder:7b",
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "num_ctx": DEFAULT_CTX,
                "temperature": DEFAULT_TEMPERATURE,
                "num_thread": DEFAULT_THREADS,
            },
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")

    async def get_status(self) -> dict:
        """Return current backend status."""
        await self.initialize()
        return {
            "backend": self.backend,
            "model_dir": str(MODEL_DIR),
            "default_model": DEFAULT_MODEL,
            "ctx_size": DEFAULT_CTX,
            "threads": DEFAULT_THREADS,
            "gpu_layers": DEFAULT_GPU_LAYERS,
        }

    async def list_models(self) -> list[dict]:
        """List available models."""
        models = []
        # Check GGUF files
        if MODEL_DIR.exists():
            for f in MODEL_DIR.glob("*.gguf"):
                models.append({"name": f.stem, "path": str(f), "size_gb": round(f.stat().st_size / 1e9, 1)})
        # Check Ollama
        if self.backend == "ollama":
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get("http://localhost:11434/api/tags", timeout=5)
                    if resp.status_code == 200:
                        for m in resp.json().get("models", []):
                            models.append({"name": m["name"], "path": "ollama", "size_gb": round(m.get("size", 0) / 1e9, 1)})
            except Exception:
                pass
        return models


# Singleton — drop-in replacement for the old ollama service
llm = LLMService()
