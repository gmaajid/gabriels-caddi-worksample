"""Tests for document loaders and enrichment pipeline."""

from pathlib import Path

from rag.loaders import (
    _detect_csv_type,
    _enrich_inspection_row,
    _enrich_order_row,
    _enrich_rfq_row,
    load_csv,
    load_directory,
    load_file,
    load_text,
)
from src.models import init_supplier_normalizer


def setup_module():
    init_supplier_normalizer(["APEX MFG", "Apex Manufacturing Inc", "AeroFlow Systems"])


# --- CSV type detection ---

def test_detect_supplier_orders():
    assert _detect_csv_type(Path("x.csv"), ["order_id", "supplier_name", "unit_price"]) == "supplier_orders"


def test_detect_quality_inspections():
    assert _detect_csv_type(Path("x.csv"), ["inspection_id", "order_id"]) == "quality_inspections"


def test_detect_rfq_responses():
    assert _detect_csv_type(Path("x.csv"), ["rfq_id", "supplier_name", "quoted_price"]) == "rfq_responses"


def test_detect_unknown():
    assert _detect_csv_type(Path("x.csv"), ["foo", "bar"]) == "unknown"


# --- Row enrichment ---

def test_enrich_order_row():
    row = {"supplier_name": "APEX MFG", "order_id": "PO-001"}
    enriched = _enrich_order_row(row)
    assert "supplier_canonical" in enriched
    assert enriched["order_id"] == "PO-001"  # original preserved


def test_enrich_inspection_row_known():
    row = {"rejection_reason": "Burrs on edges"}
    enriched = _enrich_inspection_row(row)
    assert enriched["severity"] == "machining"


def test_enrich_inspection_row_unknown():
    row = {"rejection_reason": "Something never seen before"}
    enriched = _enrich_inspection_row(row)
    assert enriched["severity"] == "unknown"


def test_enrich_rfq_row():
    row = {"supplier_name": "AeroFlow Systems", "rfq_id": "RFQ-001"}
    enriched = _enrich_rfq_row(row)
    assert "supplier_canonical" in enriched


# --- CSV loading with enrichment ---

def test_load_csv_supplier_orders(tmp_path):
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(
        "order_id,supplier_name,unit_price\n"
        "PO-001,APEX MFG,100.0\n"
        "PO-002,AeroFlow Systems,200.0\n"
    )
    docs = load_csv(csv_file, chunk_size=1)
    assert len(docs) == 2
    assert docs[0]["metadata"]["dataset"] == "supplier_orders"
    assert "supplier_canonical" in docs[0]["text"]


def test_load_csv_inspections(tmp_path):
    csv_file = tmp_path / "inspections.csv"
    csv_file.write_text(
        "inspection_id,order_id,rejection_reason\n"
        "INS-001,PO-001,Passed\n"
    )
    docs = load_csv(csv_file, chunk_size=1)
    assert docs[0]["metadata"]["dataset"] == "quality_inspections"
    assert "severity: passed" in docs[0]["text"]


def test_load_csv_rfq(tmp_path):
    csv_file = tmp_path / "rfq.csv"
    csv_file.write_text(
        "rfq_id,supplier_name,quoted_price\n"
        "RFQ-001,APEX MFG,50.0\n"
    )
    docs = load_csv(csv_file, chunk_size=1)
    assert docs[0]["metadata"]["dataset"] == "rfq_responses"


def test_load_csv_unknown_type(tmp_path):
    csv_file = tmp_path / "generic.csv"
    csv_file.write_text("foo,bar\n1,2\n3,4\n")
    docs = load_csv(csv_file, chunk_size=1)
    assert docs[0]["metadata"]["dataset"] == "unknown"
    # No enrichment applied, but still loads
    assert "foo: 1" in docs[0]["text"]


# --- Text loading ---

def test_load_text_md(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# Title\n\nSome content.")
    docs = load_text(f)
    assert docs[0]["metadata"]["type"] == "md"


def test_load_text_txt(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("Plain text notes here.")
    docs = load_text(f)
    assert docs[0]["metadata"]["type"] == "txt"


# --- load_file auto-detection ---

def test_load_file_csv(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    docs = load_file(f)
    assert docs[0]["metadata"]["type"] == "csv"


def test_load_file_unknown_extension(tmp_path):
    f = tmp_path / "data.jsonl"
    f.write_text('{"key": "value"}\n')
    docs = load_file(f)
    # Falls back to text loader
    assert docs[0]["metadata"]["type"] == "jsonl"


# --- load_directory ---

def test_load_directory(tmp_path):
    (tmp_path / "a.csv").write_text("x,y\n1,2\n")
    (tmp_path / "b.md").write_text("# Hello")
    (tmp_path / ".hidden").write_text("skip me")
    docs = load_directory(tmp_path)
    sources = {d["metadata"]["source"] for d in docs}
    assert "a.csv" in sources
    assert "b.md" in sources
    assert ".hidden" not in sources


def test_load_directory_nonexistent(tmp_path):
    docs = load_directory(tmp_path / "nonexistent")
    assert docs == []
