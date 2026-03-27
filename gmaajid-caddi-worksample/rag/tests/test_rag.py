"""Tests for the RAG system."""

import tempfile
from pathlib import Path

from rag.chunking import chunk_csv_rows, chunk_text
from rag.core import RAGEngine
from rag.loaders import load_csv, load_text


def test_chunk_text_short():
    text = "Short text."
    assert chunk_text(text) == ["Short text."]


def test_chunk_text_splits():
    text = "A" * 600 + ". " + "B" * 600
    chunks = chunk_text(text, chunk_size=512, overlap=64)
    assert len(chunks) >= 2


def test_chunk_csv_rows():
    rows = [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
    chunks = chunk_csv_rows(rows, rows_per_chunk=1)
    assert len(chunks) == 2
    assert "a: 1" in chunks[0]


def test_load_csv(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,value\nalice,10\nbob,20\n")
    docs = load_csv(csv_file, chunk_size=1)
    assert len(docs) == 2
    assert docs[0]["metadata"]["source"] == "test.csv"


def test_load_text(tmp_path):
    txt_file = tmp_path / "test.md"
    txt_file.write_text("# Hello\n\nSome content here.")
    docs = load_text(txt_file)
    assert len(docs) >= 1
    assert docs[0]["metadata"]["type"] == "md"


def test_engine_ingest_and_query():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RAGEngine(persist_dir=Path(tmpdir) / "db", collection_name="test")
        engine.ingest_text("Apex Manufacturing supplies heat exchangers for data centers.", source="test")
        engine.ingest_text("QuickFab Industries offers low-cost steel brackets.", source="test")

        assert engine.count >= 2

        results = engine.query("heat exchangers", top_k=2)
        assert len(results) > 0
        assert "heat exchanger" in results[0]["text"].lower()


def test_engine_query_with_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RAGEngine(persist_dir=Path(tmpdir) / "db", collection_name="test")
        engine.ingest_text("Hoth Industries needs HEPA filters for clean rooms.", source="test")

        ctx = engine.query_with_context("HEPA filters")
        assert "HEPA" in ctx
        assert "source: test" in ctx
