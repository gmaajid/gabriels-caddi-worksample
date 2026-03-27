.PHONY: setup test test-cov clean docker-build docker-run help

CLI = ./caddi-cli

# ─── Help ───────────────────────────────────────────────────────────────

help:
	@echo "CADDi Supply Chain RAG"
	@echo ""
	@echo "Make targets (setup/build/test):"
	@echo "  make setup          Create venv and install dependencies"
	@echo "  make test           Run all tests"
	@echo "  make test-cov       Run tests with coverage report"
	@echo "  make clean          Delete the vector store"
	@echo "  make docker-build   Build the Docker image"
	@echo "  make docker-run     Run the Docker container"
	@echo ""
	@echo "All other commands use caddi-cli directly:"
	@echo "  ./caddi-cli --help"
	@echo ""

# ─── Setup ────────────────────────────────────────────────────────────

setup:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	@echo ""
	@echo "Setup complete. Run: ./caddi-cli --help"

# ─── Testing ──────────────────────────────────────────────────────────

test:
	.venv/bin/pytest rag/tests/ src/tests/ -v

test-cov:
	.venv/bin/pytest rag/tests/ src/tests/ --cov=rag --cov=src --cov-report=term-missing

# ─── Clean ────────────────────────────────────────────────────────────

clean:
	rm -rf data/chroma_db/
	@echo "Vector store cleared. Run './caddi-cli ingest' to rebuild."

# ─── Docker ───────────────────────────────────────────────────────────

docker-build:
	docker build -t caddi-worksample .

docker-run:
	docker run -it --rm -e ANTHROPIC_API_KEY caddi-worksample
