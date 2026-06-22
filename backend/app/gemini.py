"""Gemini client wrapper.

Key design decisions (see memory: the free-tier key only works on
gemini-2.5-flash and rate-limits aggressively):
  * concurrency is capped by a semaphore
  * 429 / transient errors are retried with exponential backoff
  * failures are LOGGED, never silently swallowed into empty results
  * when no key is configured the client reports unavailable and callers
    fall back to the deterministic heuristic engine
"""
from __future__ import annotations

import json
import asyncio
import logging
import hashlib

import numpy as np

from app.config import get_settings

logger = logging.getLogger("recruitiq.gemini")
settings = get_settings()

try:
    from google import genai
    from google.genai import types
    from google.genai import errors as genai_errors
except Exception:  # pragma: no cover - import guard
    genai = None
    types = None
    genai_errors = None


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg or "UNAVAILABLE" in msg


def _is_daily_exhausted(exc: Exception) -> bool:
    """A per-DAY free-tier cap. Unlike per-minute limits, retrying within a run
    is pointless (it won't reset for hours), so we fail fast to the heuristic
    engine instead of burning ~45s of backoff per call."""
    msg = str(exc)
    return "429" in msg and ("PerDay" in msg or "per day" in msg or "RequestsPerDay" in msg)


class GeminiClient:
    def __init__(self) -> None:
        self._client = None
        self._sem = asyncio.Semaphore(settings.max_concurrency)
        self._embed_cache: dict[str, list[float]] = {}
        # Circuit breaker: once the daily quota is hit, skip API calls (and their
        # backoff) for a cooldown so the rest of the run falls back instantly.
        self._cooldown_until = 0.0
        if settings.use_real_ai and genai is not None:
            try:
                self._client = genai.Client(api_key=settings.gemini_api_key)
            except Exception as e:  # pragma: no cover
                logger.error("Failed to init Gemini client: %s", e)
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Core call with retry + backoff
    # ------------------------------------------------------------------
    async def _generate(self, system: str, user: str, *, json_mode: bool,
                        max_tokens: int, temperature: float) -> str:
        assert self._client is not None
        # Circuit breaker: daily quota exhausted -> skip the call entirely.
        loop = asyncio.get_event_loop()
        if loop.time() < self._cooldown_until:
            raise RuntimeError("Gemini daily quota cooldown active")
        cfg_kwargs = dict(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        # Disable "thinking" — these are extraction/judgement tasks, not chain-of-
        # thought puzzles. Thinking roughly doubles latency and token cost on
        # 2.5-flash, which blows the <60s budget for a 20+ CV batch.
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:  # pragma: no cover - older SDKs
            pass
        if json_mode:
            cfg_kwargs["response_mime_type"] = "application/json"

        last_exc: Exception | None = None
        for attempt in range(settings.max_retries):
            async with self._sem:
                try:
                    resp = await self._client.aio.models.generate_content(
                        model=settings.gemini_model,
                        contents=user,
                        config=types.GenerateContentConfig(**cfg_kwargs),
                    )
                    return resp.text or ""
                except Exception as e:
                    last_exc = e
                    if _is_daily_exhausted(e):
                        # No point retrying a per-day cap. Arm the breaker so the
                        # rest of this run skips the API and uses heuristics.
                        self._cooldown_until = loop.time() + 300
                        logger.error("Gemini DAILY quota exhausted — switching to "
                                     "heuristic mode for 5 min. Enable billing to lift this.")
                        break
                    if _is_rate_limit(e) and attempt < settings.max_retries - 1:
                        delay = settings.retry_base_delay * (2 ** attempt)
                        logger.warning("Gemini 429/transient (attempt %d), backing off %.1fs",
                                       attempt + 1, delay)
                    else:
                        break
            # sleep OUTSIDE the semaphore so a backing-off call frees its slot
            if last_exc and _is_rate_limit(last_exc) and not _is_daily_exhausted(last_exc) \
                    and attempt < settings.max_retries - 1:
                await asyncio.sleep(settings.retry_base_delay * (2 ** attempt))

        logger.error("Gemini generate failed after %d attempts: %s",
                     settings.max_retries, last_exc)
        raise last_exc if last_exc else RuntimeError("Gemini call failed")

    async def generate_json(self, system: str, user: str, *,
                            max_tokens: int = 2048, temperature: float = 0.2) -> dict | list:
        raw = await self._generate(system, user, json_mode=True,
                                   max_tokens=max_tokens, temperature=temperature)
        return _loads(raw)

    async def generate_text(self, system: str, user: str, *,
                            max_tokens: int = 1024, temperature: float = 0.5) -> str:
        return await self._generate(system, user, json_mode=False,
                                    max_tokens=max_tokens, temperature=temperature)

    # ------------------------------------------------------------------
    # Embeddings (cheap, high quota, batchable)
    # ------------------------------------------------------------------
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed, serving cache hits for free. Falls back to a
        deterministic hash embedding if the API is unavailable/failing."""
        if not texts:
            return []
        results: list[list[float] | None] = [None] * len(texts)
        miss_idx, miss_texts = [], []
        for i, t in enumerate(texts):
            key = _hash(t)
            if key in self._embed_cache:
                results[i] = self._embed_cache[key]
            else:
                miss_idx.append(i)
                miss_texts.append(t)

        if miss_texts:
            embs = await self._embed_api(miss_texts)
            for i, t, e in zip(miss_idx, miss_texts, embs):
                self._embed_cache[_hash(t)] = e
                results[i] = e
        return [r for r in results]  # all filled

    async def _embed_api(self, texts: list[str]) -> list[list[float]]:
        if not self.available:
            return [_mock_embedding(t) for t in texts]
        # API caps batch size; chunk to be safe.
        out: list[list[float]] = []
        for chunk in _chunks(texts, 100):
            for attempt in range(settings.max_retries):
                try:
                    async with self._sem:
                        resp = await self._client.aio.models.embed_content(
                            model=settings.embedding_model,
                            contents=[t[:8000] for t in chunk],
                            config=types.EmbedContentConfig(
                                output_dimensionality=settings.embedding_dim),
                        )
                    out.extend(list(e.values) for e in resp.embeddings)
                    break
                except Exception as e:
                    if _is_rate_limit(e) and attempt < settings.max_retries - 1:
                        await asyncio.sleep(settings.retry_base_delay * (2 ** attempt))
                        continue
                    logger.error("Embedding failed, using mock fallback: %s", e)
                    out.extend(_mock_embedding(t) for t in chunk)
                    break
        return out


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _loads(raw: str) -> dict | list:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty model response")
    # Strip markdown fences if the model wrapped JSON in them.
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1] if "```" in raw[3:] else raw.strip("`")
        raw = raw.removeprefix("json").strip()
    return json.loads(raw)


def _mock_embedding(text: str) -> list[float]:
    """Deterministic pseudo-embedding so similarity is stable without the API."""
    h = hashlib.sha256(text.lower().encode()).digest()
    vec = np.frombuffer(h * 24, dtype=np.uint8).astype(np.float32)[:settings.embedding_dim]
    vec = (vec - vec.mean()) / (vec.std() + 1e-8)
    return vec.tolist()


gemini = GeminiClient()
