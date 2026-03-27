"""Self-contained RAG system for CADDi supply chain intelligence."""

import logging
import os
import warnings

# Suppress third-party noise BEFORE any imports trigger model loading
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["SAFETENSORS_FAST_GPU"] = "0"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TQDM_DISABLE"] = "1"
warnings.filterwarnings("ignore", category=FutureWarning)

# Configure project-level logging
logging.basicConfig(
    format="%(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

# Suppress noisy third-party loggers
for _name in [
    "sentence_transformers",
    "transformers",
    "transformers.utils.loading_report",
    "chromadb",
    "httpx",
    "tqdm",
]:
    logging.getLogger(_name).setLevel(logging.ERROR)

from rag.core import RAGEngine

__all__ = ["RAGEngine"]
