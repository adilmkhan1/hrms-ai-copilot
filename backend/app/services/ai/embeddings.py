"""Embedding utility — wraps OpenAI text-embedding-3-small."""

from __future__ import annotations

import logging
from typing import List

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Return a list of embedding vectors for the given texts.

    Batches requests in groups of 100 to stay within API limits.
    """
    if not texts:
        return []

    client = _get_client()
    results: List[List[float]] = []

    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await client.embeddings.create(
            input=batch,
            model=settings.openai_embedding_model,
        )
        results.extend([item.embedding for item in response.data])

    return results


async def embed_single(text: str) -> List[float]:
    """Convenience wrapper for embedding a single string."""
    vectors = await embed_texts([text])
    return vectors[0]
