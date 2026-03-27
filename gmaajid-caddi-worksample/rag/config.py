"""RAG configuration — single source of truth for all paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # rag/config.py -> project root
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
KNOWLEDGE_DIR = DOCS_DIR / "knowledge"
CHROMA_DIR = DATA_DIR / "chroma_db"

CONFIRMED_MAPPINGS_PATH = CONFIG_DIR / "confirmed_mappings.yaml"
REVIEWER_CONFIG_PATH = CONFIG_DIR / "reviewer.yaml"
REVIEW_DIR = CONFIG_DIR / "review"
REVIEW_CANDIDATES_PATH = REVIEW_DIR / "review_candidates.yaml"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "caddi_supply_chain"

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
TOP_K = 8
