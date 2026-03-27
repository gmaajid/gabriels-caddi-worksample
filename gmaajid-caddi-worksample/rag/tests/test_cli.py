"""Tests for CLI interface."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from rag.cli import cli
from rag.core import RAGEngine


runner = CliRunner()


def _make_engine(tmpdir):
    """Create a RAGEngine in a temp dir with some test data."""
    engine = RAGEngine(persist_dir=Path(tmpdir) / "db", collection_name="cli_test")
    engine.ingest_text("Heat exchangers are used in data centers.", source="test")
    engine.ingest_text("HEPA filters for industrial use.", source="test")
    return engine


def test_cli_help():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "CADDi Supply Chain RAG" in result.output


def test_status_command():
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "Vector store" in result.output
    assert "Total chunks" in result.output


def test_add_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Some test content for ingestion.")
    result = runner.invoke(cli, ["add", str(f)])
    assert result.exit_code == 0
    assert "Added" in result.output


def test_add_directory(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "a.txt").write_text("Content A")
    (d / "b.md").write_text("Content B")
    result = runner.invoke(cli, ["add", str(d)])
    assert result.exit_code == 0
    assert "Added" in result.output


def test_ingest_command(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "test.csv").write_text("a,b\n1,2\n")
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "info.md").write_text("# Test knowledge")

    result = runner.invoke(cli, [
        "ingest",
        "--data-dir", str(data_dir),
        "--knowledge-dir", str(knowledge_dir),
    ])
    assert result.exit_code == 0
    assert "Done" in result.output


def test_query_raw():
    """Query with --raw flag shows table output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine(tmpdir)
        with patch("rag.core.RAGEngine", return_value=engine):
            result = runner.invoke(cli, ["query", "heat exchangers", "--raw"])
            assert result.exit_code == 0


def test_query_with_llm_mock():
    """Query without --raw uses LLM (mocked)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine(tmpdir)
        with patch("rag.core.RAGEngine", return_value=engine):
            with patch("rag.llm.ask", return_value="Mocked LLM answer"):
                result = runner.invoke(cli, ["query", "quality data"])
                assert result.exit_code == 0


def test_chat_quit():
    """Chat command exits on 'quit' input."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine(tmpdir)
        with patch("rag.core.RAGEngine", return_value=engine):
            result = runner.invoke(cli, ["chat"], input="quit\n")
            assert result.exit_code == 0


def test_chat_empty_input():
    """Chat handles empty input then quit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine(tmpdir)
        with patch("rag.core.RAGEngine", return_value=engine):
            result = runner.invoke(cli, ["chat"], input="\nquit\n")
            assert result.exit_code == 0


def test_chat_one_question():
    """Chat handles one question then quit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine(tmpdir)
        with patch("rag.core.RAGEngine", return_value=engine):
            with patch("rag.llm.ask", return_value="Mocked response"):
                result = runner.invoke(cli, ["chat"], input="filters\nquit\n")
                assert result.exit_code == 0
