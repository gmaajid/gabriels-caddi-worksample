"""Core RAG engine: embed, store, retrieve, with transaction log for rollback."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import chromadb
import yaml
from sentence_transformers import SentenceTransformer

from rag.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL, TOP_K

TRANSACTION_LOG = Path(__file__).resolve().parent.parent / "config" / "rag_transactions.yaml"


class RAGEngine:
    """Self-contained RAG engine using ChromaDB + sentence-transformers.

    Every ingest operation creates a transaction with a unique ID.
    Transactions are logged to config/rag_transactions.yaml so they
    can be reverted (chunks deleted by ID).
    """

    def __init__(
        self,
        persist_dir: Path | None = None,
        model_name: str = EMBEDDING_MODEL,
        collection_name: str = COLLECTION_NAME,
    ):
        self.persist_dir = persist_dir or CHROMA_DIR
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.model = SentenceTransformer(model_name)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        # Active transaction state
        self._active_txn: Optional[str] = None
        self._txn_chunk_ids: list[str] = []
        self._txn_sources: set[str] = set()

    @property
    def count(self) -> int:
        return self.collection.count()

    def begin_transaction(self, txn_id: Optional[str] = None) -> str:
        """Start a new transaction. Returns the transaction ID."""
        self._active_txn = txn_id or generate_txn_id()
        self._txn_chunk_ids = []
        self._txn_sources = set()
        return self._active_txn

    def commit_transaction(self) -> Optional[str]:
        """Commit the active transaction to the log. Returns txn_id or None."""
        if not self._active_txn or not self._txn_chunk_ids:
            txn_id = self._active_txn
            self._active_txn = None
            self._txn_chunk_ids = []
            self._txn_sources = set()
            return txn_id

        _log_transaction(
            self._active_txn,
            self._txn_chunk_ids,
            sorted(self._txn_sources),
        )
        txn_id = self._active_txn
        self._active_txn = None
        self._txn_chunk_ids = []
        self._txn_sources = set()
        return txn_id

    def ingest_file(self, path: Path, txn_id: Optional[str] = None) -> int:
        """Ingest a single file. Returns number of chunks added."""
        from rag.loaders import load_file
        docs = load_file(path)
        return self._add_docs(docs, txn_id=txn_id)

    def ingest_directory(self, directory: Path, txn_id: Optional[str] = None) -> int:
        """Ingest all files in a directory. Returns number of chunks added."""
        from rag.loaders import load_directory
        docs = load_directory(directory)
        return self._add_docs(docs, txn_id=txn_id)

    def ingest_text(self, text: str, source: str = "manual", txn_id: Optional[str] = None) -> int:
        """Ingest a raw text string."""
        from rag.chunking import chunk_text

        chunks = chunk_text(text)
        docs = [
            {"text": c, "metadata": {"source": source, "type": "text", "chunk_index": i}}
            for i, c in enumerate(chunks)
        ]
        return self._add_docs(docs, txn_id=txn_id)

    def query(self, question: str, top_k: int = TOP_K) -> list[dict]:
        """Query the vector store. Returns list of {text, metadata, distance}."""
        if self.count == 0:
            return []
        embedding = self.model.encode([question]).tolist()
        results = self.collection.query(
            query_embeddings=embedding,
            n_results=min(top_k, self.count),
        )
        hits = []
        for i in range(len(results["ids"][0])):
            hits.append(
                {
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                }
            )
        return hits

    def query_with_context(self, question: str, top_k: int = TOP_K) -> str:
        """Query and format results as a context string for an LLM."""
        hits = self.query(question, top_k=top_k)
        if not hits:
            return "No relevant context found in the knowledge base."
        parts = []
        for i, hit in enumerate(hits, 1):
            source = hit["metadata"].get("source", "unknown")
            parts.append(f"[{i}] (source: {source}, relevance: {1 - hit['distance']:.2f})\n{hit['text']}")
        return "\n\n---\n\n".join(parts)

    def revert_transaction(self, txn_id: str) -> int:
        """Delete all chunks added by a specific transaction. Returns count deleted."""
        txn_log = _load_transaction_log()
        txn = next((t for t in txn_log.get("transactions", []) if t["txn_id"] == txn_id), None)
        if txn is None:
            raise ValueError(f"Transaction '{txn_id}' not found in log")
        if txn.get("reverted"):
            raise ValueError(f"Transaction '{txn_id}' already reverted")

        chunk_ids = txn.get("chunk_ids", [])
        if chunk_ids:
            self.collection.delete(ids=chunk_ids)

        txn["reverted"] = True
        txn["reverted_at"] = datetime.now().isoformat()
        _save_transaction_log(txn_log)

        return len(chunk_ids)

    def _add_docs(self, docs: list[dict], txn_id: Optional[str] = None) -> int:
        if not docs:
            return 0

        # Use active transaction if no explicit txn_id
        effective_txn = txn_id or self._active_txn

        # Generate unique chunk IDs
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        ids = [f"chunk_{ts}_{i:04d}" for i in range(len(docs))]

        texts = [d["text"] for d in docs]
        metadatas = [d["metadata"] for d in docs]

        if effective_txn:
            for m in metadatas:
                m["txn_id"] = effective_txn

        embeddings = self.model.encode(texts).tolist()
        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        # If using active transaction, accumulate; otherwise log immediately
        if self._active_txn:
            self._txn_chunk_ids.extend(ids)
            for d in docs:
                self._txn_sources.add(d["metadata"].get("source", ""))
        elif txn_id:
            # Standalone call with explicit txn_id — log immediately
            _log_transaction(txn_id, ids, [d["metadata"].get("source", "") for d in docs])

        return len(docs)


# ---------------------------------------------------------------------------
# Transaction log (config/rag_transactions.yaml)
# ---------------------------------------------------------------------------

def _load_transaction_log(path: Path = TRANSACTION_LOG) -> dict:
    if not path.exists():
        return {"transactions": []}
    with open(path) as f:
        return yaml.safe_load(f) or {"transactions": []}


def _save_transaction_log(data: dict, path: Path = TRANSACTION_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _log_transaction(txn_id: str, chunk_ids: list[str], sources: list[str]) -> None:
    log = _load_transaction_log()
    log["transactions"].append({
        "txn_id": txn_id,
        "created": datetime.now().isoformat(),
        "chunk_count": len(chunk_ids),
        "chunk_ids": chunk_ids,
        "sources": sorted(set(s for s in sources if s)),
        "reverted": False,
    })
    _save_transaction_log(log)


def generate_txn_id() -> str:
    """Generate a unique transaction ID."""
    return f"txn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def list_transactions(path: Path = TRANSACTION_LOG) -> list[dict]:
    """List all transactions with summary info."""
    log = _load_transaction_log(path)
    return log.get("transactions", [])
