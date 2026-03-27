"""Document loaders for various file types."""

from __future__ import annotations

import csv
from pathlib import Path

from rag.chunking import chunk_csv_rows, chunk_text
from src.models import (
    normalize_supplier,
    REJECTION_SEVERITY_MAP,
)


def _detect_csv_type(path: Path, headers: list[str]) -> str:
    """Detect which dataset a CSV belongs to based on column names."""
    header_set = set(headers)
    if "order_id" in header_set and "unit_price" in header_set:
        return "supplier_orders"
    if "inspection_id" in header_set:
        return "quality_inspections"
    if "rfq_id" in header_set:
        return "rfq_responses"
    return "unknown"


def _enrich_order_row(row: dict) -> dict:
    """Add normalized supplier name to an order row."""
    enriched = dict(row)
    enriched["supplier_canonical"] = normalize_supplier(row.get("supplier_name", ""))
    return enriched


def _enrich_inspection_row(row: dict) -> dict:
    """Add severity classification to an inspection row."""
    enriched = dict(row)
    reason = row.get("rejection_reason", "")
    severity = REJECTION_SEVERITY_MAP.get(reason)
    enriched["severity"] = severity.value if severity else "unknown"
    return enriched


def _enrich_rfq_row(row: dict) -> dict:
    """Add normalized supplier name to an RFQ row."""
    enriched = dict(row)
    enriched["supplier_canonical"] = normalize_supplier(row.get("supplier_name", ""))
    return enriched


_ENRICHERS = {
    "supplier_orders": _enrich_order_row,
    "quality_inspections": _enrich_inspection_row,
    "rfq_responses": _enrich_rfq_row,
}


def load_csv(path: Path, chunk_size: int = 10) -> list[dict]:
    """Load a CSV file, enrich with normalized data, and return chunked documents."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    csv_type = _detect_csv_type(path, headers)
    enricher = _ENRICHERS.get(csv_type)
    if enricher:
        rows = [enricher(row) for row in rows]

    chunks = chunk_csv_rows(rows, rows_per_chunk=chunk_size)
    source = path.name
    return [
        {
            "text": chunk,
            "metadata": {"source": source, "type": "csv", "dataset": csv_type, "chunk_index": i},
        }
        for i, chunk in enumerate(chunks)
    ]


def load_text(path: Path, chunk_size: int = 512, overlap: int = 64) -> list[dict]:
    """Load a text/markdown file and return chunked documents."""
    text = path.read_text(encoding="utf-8")
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    source = path.name
    return [
        {
            "text": chunk,
            "metadata": {"source": source, "type": path.suffix.lstrip("."), "chunk_index": i},
        }
        for i, chunk in enumerate(chunks)
    ]


LOADER_MAP = {
    ".csv": load_csv,
    ".txt": load_text,
    ".md": load_text,
}


def load_file(path: Path) -> list[dict]:
    """Auto-detect file type and load."""
    loader = LOADER_MAP.get(path.suffix.lower())
    if loader is None:
        # Fall back to plain text for unknown extensions
        return load_text(path)
    return loader(path)


def load_directory(directory: Path) -> list[dict]:
    """Load all supported files from a directory."""
    docs = []
    if not directory.exists():
        return docs
    for path in sorted(directory.iterdir()):
        if path.is_file() and not path.name.startswith("."):
            docs.extend(load_file(path))
    return docs
