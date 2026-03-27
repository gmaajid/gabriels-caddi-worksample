"""Text chunking strategies for document ingestion."""

from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Split text into overlapping chunks by character count, breaking at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try to break at a sentence boundary
            for sep in ("\n\n", "\n", ". ", ", ", " "):
                boundary = text.rfind(sep, start + chunk_size // 2, end)
                if boundary != -1:
                    end = boundary + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else len(text)
    return chunks


def chunk_csv_rows(rows: list[dict], rows_per_chunk: int = 10) -> list[str]:
    """Convert CSV rows into text chunks, grouping rows together."""
    chunks = []
    for i in range(0, len(rows), rows_per_chunk):
        batch = rows[i : i + rows_per_chunk]
        lines = []
        for row in batch:
            line = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
            lines.append(line)
        chunks.append("\n".join(lines))
    return chunks
