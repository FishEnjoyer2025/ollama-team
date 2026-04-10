import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)


async def check_health(
    url: str = "http://localhost:8000/health",
    timeout: float = 60.0,
    retries: int = 3,
    retry_delay: float = 5.0,
) -> bool:
    """Hit the health endpoint. Returns True if healthy within timeout."""
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    logger.info(f"Health check passed (attempt {attempt + 1})")
                    return True
        except Exception as e:
            logger.warning(f"Health check attempt {attempt + 1} failed: {e}")

        if attempt < retries - 1:
            await asyncio.sleep(retry_delay)

    logger.error(f"Health check failed after {retries} attempts")
    return False
