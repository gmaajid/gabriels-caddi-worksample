"""Additional tests for RAG core engine to improve coverage."""

import tempfile
from pathlib import Path

from rag.core import RAGEngine


def test_ingest_file(tmp_path):
    db_dir = tmp_path / "db"
    engine = RAGEngine(persist_dir=db_dir, collection_name="test_file")

    txt = tmp_path / "doc.txt"
    txt.write_text("Information about heat exchangers and cooling systems.")
    n = engine.ingest_file(txt)
    assert n >= 1
    assert engine.count >= 1


def test_ingest_directory(tmp_path):
    db_dir = tmp_path / "db"
    engine = RAGEngine(persist_dir=db_dir, collection_name="test_dir")

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.txt").write_text("Supplier performance data.")
    (docs_dir / "b.md").write_text("# Quality metrics")
    n = engine.ingest_directory(docs_dir)
    assert n >= 2


def test_ingest_text_multiple():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RAGEngine(persist_dir=Path(tmpdir) / "db", collection_name="test_multi")
        engine.ingest_text("First document about suppliers.", source="s1")
        engine.ingest_text("Second document about quality.", source="s2")
        engine.ingest_text("Third document about procurement.", source="s3")
        assert engine.count == 3


def test_query_empty_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RAGEngine(persist_dir=Path(tmpdir) / "db", collection_name="test_empty")
        results = engine.query("anything")
        assert results == []


def test_query_with_context_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RAGEngine(persist_dir=Path(tmpdir) / "db", collection_name="test_ctx_empty")
        ctx = engine.query_with_context("anything")
        assert "No relevant context" in ctx


def test_count_property():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RAGEngine(persist_dir=Path(tmpdir) / "db", collection_name="test_count")
        assert engine.count == 0
        engine.ingest_text("test", source="test")
        assert engine.count == 1
