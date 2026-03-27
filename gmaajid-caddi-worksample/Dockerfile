FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml caddi-cli ./
COPY rag/ rag/
COPY src/ src/
COPY config/ config/
COPY data/ data/
COPY web/ web/
COPY docs/ docs/

# Make caddi-cli executable
RUN chmod +x caddi-cli

# Install dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Pre-download the embedding model (cached in image layer)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8080

ENTRYPOINT ["./caddi-cli"]
CMD ["--help"]
