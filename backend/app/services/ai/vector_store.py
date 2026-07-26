"""ChromaDB vector store manager for HR policy documents.

Collections:
  - hr_policies : chunks of HR policy text with metadata

Usage:
    store = get_vector_store()
    await store.upsert_policy(policy_id=1, chunks=["...", "..."], metadata={})
    results = await store.search(query="sick leave", k=5)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.services.ai.embeddings import embed_texts

logger = logging.getLogger(__name__)

POLICY_COLLECTION = "hr_policies"


@dataclass
class SearchResult:
    chunk_text: str
    policy_id: int
    policy_title: str
    policy_category: str
    original_filename: Optional[str]
    distance: float


class HRPolicyVectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.chroma_db_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=POLICY_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def upsert_policy_chunks(
        self,
        policy_id: int,
        chunks: List[str],
        policy_title: str,
        policy_category: str,
        original_filename: Optional[str] = None,
    ) -> None:
        """Embed and upsert all chunks for a policy. Existing chunks for this
        policy_id are deleted first to avoid stale duplicates."""
        # Delete old chunks for this policy
        existing = self._collection.get(where={"policy_id": policy_id})
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])

        if not chunks:
            return

        # Generate embeddings (run sync ChromaDB in thread to avoid blocking)
        embeddings = await embed_texts(chunks)

        ids = [f"policy_{policy_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas: List[Dict[str, Any]] = [
            {
                "policy_id": policy_id,
                "policy_title": policy_title,
                "policy_category": policy_category,
                "original_filename": original_filename or "",
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            ),
        )
        logger.info(
            "Upserted %d chunks for policy_id=%d (%s)",
            len(chunks),
            policy_id,
            policy_title,
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self, query: str, k: int = 5
    ) -> List[SearchResult]:
        """Return the top-k most similar chunks to the query."""
        from app.services.ai.embeddings import embed_single

        query_embedding = await embed_single(query)

        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(k, max(1, self._collection.count())),
                include=["documents", "metadatas", "distances"],
            ),
        )

        search_results: List[SearchResult] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            search_results.append(
                SearchResult(
                    chunk_text=doc,
                    policy_id=int(meta.get("policy_id", 0)),
                    policy_title=str(meta.get("policy_title", "")),
                    policy_category=str(meta.get("policy_category", "")),
                    original_filename=meta.get("original_filename") or None,
                    distance=float(dist),
                )
            )
        return search_results

    def count(self) -> int:
        return self._collection.count()


# ── Singleton ────────────────────────────────────────────────────────────────

_store: HRPolicyVectorStore | None = None


def get_vector_store() -> HRPolicyVectorStore:
    global _store
    if _store is None:
        _store = HRPolicyVectorStore()
    return _store
