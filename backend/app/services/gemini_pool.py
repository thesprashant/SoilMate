import logging
import asyncio
from typing import List, Optional, Any, Dict
from google import genai
from google.genai import types
from app.config import settings

logger = logging.getLogger(__name__)

class GeminiKeyManager:
    """
    Manages a pool of Google Gemini API keys with round-robin rotation,
    health tracking, and automatic failover on 429 (ResourceExhausted) or 503 errors.
    """
    def __init__(self, keys: Optional[List[str]] = None):
        self.keys = keys if keys is not None else settings.gemini_api_keys
        self.current_index = 0
        self._lock = asyncio.Lock()
        self.failure_counts: Dict[str, int] = {k: 0 for k in self.keys}
        
        if not self.keys:
            logger.warning("[GeminiKeyManager] No Gemini API keys configured! Agent calls will return an unavailable error.")

    @property
    def total_keys(self) -> int:
        return len(self.keys)

    def get_active_key(self) -> Optional[str]:
        if not self.keys:
            return None
        return self.keys[self.current_index % len(self.keys)]

    async def rotate_to_next_key(self, failed_key: Optional[str] = None, reason: str = "") -> Optional[str]:
        async with self._lock:
            if not self.keys:
                return None
            if failed_key and failed_key in self.failure_counts:
                self.failure_counts[failed_key] += 1
            
            old_index = self.current_index
            self.current_index = (self.current_index + 1) % len(self.keys)
            new_key = self.keys[self.current_index]
            logger.warning(
                f"[GeminiKeyManager] Key {old_index + 1}/{len(self.keys)} failed ({reason}). "
                f"Rotating to key {self.current_index + 1}/{len(self.keys)}."
            )
            return new_key

    def get_client(self, key: Optional[str] = None) -> Optional[genai.Client]:
        active_key = key or self.get_active_key()
        if not active_key:
            return None
        return genai.Client(api_key=active_key, http_options=types.HttpOptions(timeout=30000))

    async def generate_with_fallback(
        self,
        model: str = "gemini-3.5-flash",
        contents: Any = None,
        config: Optional[types.GenerateContentConfig] = None,
        max_attempts: Optional[int] = None
    ) -> Any:
        """
        Execute generate_content with automatic key failover, model fallback,
        and progressive backoff on 503 (high demand) or 429 (rate limit).
        """
        if not self.keys:
            raise RuntimeError("No GEMINI_API_KEYS configured. Please add keys in .env.")

        # Candidate models to try in case of 503 high-demand spike on a specific model
        candidate_models = [model]
        for fallback in ["gemini-2.5-flash"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        attempts = max_attempts or max(4, len(self.keys) * 3)
        last_exception = None

        for attempt in range(attempts):
            active_key = self.get_active_key()
            client = self.get_client(active_key)
            if not client:
                raise RuntimeError("Failed to initialize Gemini client.")

            # Select model: try requested model first, then alternate if 503 occurs
            current_model = candidate_models[attempt % len(candidate_models)]

            try:
                async with client.aio as async_client:
                    response = await asyncio.wait_for(async_client.models.generate_content(model=current_model, contents=contents, config=config), 35)
                return response
            except Exception as e:
                err_str = str(e)
                for secret in self.keys:
                    err_str = err_str.replace(secret, "[redacted]")
                last_exception = e
                is_rate_limit = (
                    "429" in err_str or 
                    "RESOURCE_EXHAUSTED" in err_str or 
                    "quota" in err_str.lower() or 
                    "rate limit" in err_str.lower()
                )
                is_server_error = "500" in err_str or "503" in err_str or "unavailable" in err_str.lower() or "high demand" in err_str.lower()

                if is_rate_limit or is_server_error or "404" in err_str or isinstance(e, asyncio.TimeoutError):
                    backoff = min(1.0 * (attempt + 1), 3.0)
                    next_model = candidate_models[(attempt + 1) % len(candidate_models)]
                    logger.warning(
                        f"[GeminiKeyManager] Attempt {attempt + 1} on model '{current_model}' failed ({err_str[:90]}...). "
                        f"Backing off {backoff:.1f}s and trying fallback model '{next_model}'..."
                    )
                    await self.rotate_to_next_key(active_key, reason=err_str[:80])
                    await asyncio.sleep(backoff)
                    continue
                else:
                    # Non-retryable error
                    logger.error(f"[GeminiKeyManager] Unhandled Gemini API error on '{current_model}': {err_str}")
                    raise e

        raise RuntimeError(f"All Gemini API attempts failed after {attempts} attempts.")

# Global singleton instance
key_manager = GeminiKeyManager()

