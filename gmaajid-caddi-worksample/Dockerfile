FROM python:3.12-slim

WORKDIR /app

# Install build dependencies for sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY rag/ rag/
COPY data/ data/
COPY docs/ docs/
COPY config/ config/

RUN pip install --no-cache-dir -e .

# Pre-download the embedding model so it's baked into the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Ingest data at build time
RUN rag ingest --data-dir data/ --knowledge-dir docs/knowledge/

ENTRYPOINT ["rag"]
CMD ["chat"]
