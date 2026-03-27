# Testing Documentation

## Table of Contents

- [Overview](#overview)
- [Project Layout](#project-layout)
- [Coverage by Module](#coverage-by-module)
- [Test Files — RAG](#test-files--rag-ragtests)
  - [test_rag.py — RAG Engine Core](#test_ragpy--rag-engine-core-7-tests)
  - [test_loaders.py — Document Loaders](#test_loaderspy--document-loaders--enrichment-16-tests)
  - [test_cli.py — CLI Interface](#test_clipy--cli-interface-10-tests)
  - [test_llm.py — LLM Integration](#test_llmpy--llm-integration-3-tests)
  - [test_core_extra.py — Additional RAG Tests](#test_core_extrapy--additional-rag-engine-tests-6-tests)
- [Test Files — Domain](#test-files--domain-srctests)
  - [test_models.py — Pydantic Models](#test_modelspy--pydantic-models--normalization-23-tests)
  - [test_model_loaders.py — CSV-to-Pydantic](#test_model_loaderspy--csv-to-pydantic-loaders-6-tests)
  - [test_clustering_benchmark.py — Method Comparison](#test_clustering_benchmarkpy--method-comparison-9-tests)
  - [test_clustering_adversarial.py — Stress Tests](#test_clustering_adversarialpy--worst-case-stress-tests-9-tests)
  - [test_human_review.py — Human Review System](#test_human_reviewpy--human-review-system-12-tests)
  - [test_human_loop_e2e.py — End-to-End](#test_human_loop_e2epy--end-to-end-human-in-the-loop-7-tests)

## Overview

| Metric | Value |
|--------|-------|
| Total tests | 110 |
| Pass rate | 100% |
| Code coverage | 93% |
| Test framework | pytest |
| Coverage tool | pytest-cov |

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run a specific test file
.venv/bin/pytest src/tests/test_clustering_adversarial.py -v -s

# Run only RAG tests
.venv/bin/pytest rag/tests/ -v

# Run only domain/clustering tests
.venv/bin/pytest src/tests/ -v
```

## Project Layout

Tests live alongside the code they test:

```
rag/tests/          # RAG engine tests (5 files, 41 tests)
src/tests/          # Domain logic tests (6 files, 67 tests)
```

## Coverage by Module

### RAG Modules (`rag/`)

| Module | Stmts | Coverage | Notes |
|--------|:-----:|:--------:|-------|
| `rag/__init__.py` | 2 | 100% | |
| `rag/chunking.py` | 29 | 93% | |
| `rag/cli.py` | 121 | 88% | Interactive chat edge cases |
| `rag/config.py` | 14 | 100% | |
| `rag/core.py` | 55 | 98% | |
| `rag/llm.py` | 11 | 100% | Mocked API calls |
| `rag/loaders.py` | 60 | 100% | |

### Domain Modules (`src/`)

| Module | Stmts | Coverage | Notes |
|--------|:-----:|:--------:|-------|
| `src/models.py` | 117 | 96% | |
| `src/supplier_clustering.py` | 264 | 94% | |
| `src/human_review.py` | 112 | 99% | |

---

## Test Files — RAG (`rag/tests/`)

### `test_rag.py` — RAG Engine Core (7 tests)

| Test | What it validates |
|------|-------------------|
| `test_chunk_text_short` | Short text returns as single chunk |
| `test_chunk_text_splits` | Long text splits at sentence boundaries with overlap |
| `test_chunk_csv_rows` | CSV rows grouped into text chunks |
| `test_load_csv` | CSV file to chunked documents with metadata |
| `test_load_text` | Markdown file to chunked documents |
| `test_engine_ingest_and_query` | End-to-end: ingest text, query, relevant results ranked first |
| `test_engine_query_with_context` | Query returns formatted context string with source citations |

### `test_loaders.py` — Document Loaders & Enrichment (16 tests)

| Test | What it validates |
|------|-------------------|
| `test_detect_supplier_orders` | Headers with `order_id` + `unit_price` detected |
| `test_detect_quality_inspections` | Headers with `inspection_id` detected |
| `test_detect_rfq_responses` | Headers with `rfq_id` detected |
| `test_detect_unknown` | Unrecognized headers fall through |
| `test_enrich_order_row` | Adds `supplier_canonical` to order rows |
| `test_enrich_inspection_row_known` | Maps "Burrs on edges" to severity "machining" |
| `test_enrich_inspection_row_unknown` | Unknown rejection reason to severity "unknown" |
| `test_enrich_rfq_row` | Adds `supplier_canonical` to RFQ rows |
| `test_load_csv_*` | Full CSV enrichment + chunking for each dataset type |
| `test_load_file_unknown_extension` | Falls back to text loader |
| `test_load_directory` | Loads all files, skips hidden |
| `test_load_directory_nonexistent` | Returns empty list |

### `test_cli.py` — CLI Interface (10 tests)

| Test | What it validates |
|------|-------------------|
| `test_cli_help` | `--help` output |
| `test_status_command` | Shows vector store path and chunk count |
| `test_add_file` / `test_add_directory` | Single file and directory ingestion |
| `test_ingest_command` | Full ingest with `--data-dir` and `--knowledge-dir` |
| `test_query_raw` | `--raw` flag shows tabular results |
| `test_query_with_llm_mock` | Non-raw query calls LLM (mocked) |
| `test_chat_*` | Chat quit, empty input, one question cycle |

### `test_llm.py` — LLM Integration (3 tests)

| Test | What it validates |
|------|-------------------|
| `test_ask_without_api_key` | Returns raw context with warning |
| `test_ask_with_api_key` | Calls Anthropic API (mocked) |
| `test_system_prompt_content` | Prompt mentions Hoth Industries |

### `test_core_extra.py` — Additional RAG Engine Tests (6 tests)

| Test | What it validates |
|------|-------------------|
| `test_ingest_file` / `test_ingest_directory` | File and directory ingestion |
| `test_ingest_text_multiple` | Multiple text ingestions accumulate |
| `test_query_empty_store` | Empty store returns empty list |
| `test_query_with_context_empty` | Empty store returns "No relevant context" |
| `test_count_property` | Count tracks ingested chunks |

---

## Test Files — Domain (`src/tests/`)

### `test_models.py` — Pydantic Models & Normalization (23 tests)

| Category | Tests | What they validate |
|----------|:-----:|-------------------|
| Tokenization | 3 | Abbreviation expansion, legal suffix stripping, negative cases |
| Jaccard similarity | 3 | Identical, disjoint, and partial overlap sets |
| Clustering | 2 | Apex variants merge; 6 clusters from 9 raw names |
| Model performance | 5 | Pairwise P/R/F1 evaluation against ground truth |
| Normalizer integration | 4 | Apex variants resolve; passthrough unknown names |
| SupplierOrder | 3 | Computed `days_late`, `is_late`; on-time; missing delivery |
| QualityInspection | 2 | `rejection_rate`; severity classification |
| RFQResponse | 1 | Supplier normalization in computed field |

### `test_model_loaders.py` — CSV-to-Pydantic Loaders (6 tests)

| Test | What it validates |
|------|-------------------|
| `test_load_orders_from_csv` | CSV to list[SupplierOrder], computed fields work |
| `test_load_orders_missing_delivery` | Null delivery date handled |
| `test_load_inspections_from_csv` | CSV to list[QualityInspection], boolean parsing |
| `test_load_rfq_from_csv` | CSV to list[RFQResponse], price parsing |
| `test_build_rfq_to_po_map` | Sequential RFQ-to-PO mapping |

### `test_clustering_benchmark.py` — Method Comparison (9 tests)

Compares Jaccard vs Embedding vs Hybrid vs Hybrid v2 vs Pipeline across 6 scenarios.

| Scenario | Names | Groups | What it tests |
|----------|:-----:|:------:|---------------|
| Real Data | 9 | 6 | Actual Hoth Industries supplier names |
| Confusables | 10 | 5 | Names sharing tokens but different companies |
| Abbreviations | 13 | 4 | Multiple abbreviation patterns stacked |
| Typos | 10 | 3 | Character-level errors |
| Semantic | 11 | 4 | Meaning-equivalent names |
| Mixed | 24 | 8 | All challenges combined |

### `test_clustering_adversarial.py` — Worst-Case Stress Tests (9 tests)

Adversarial scenarios designed to break the clustering. These are **diagnostic** — they expose limits rather than gate on pass/fail.

| Scenario | Challenge |
|----------|-----------|
| Misspell+Abbrev | Combined misspellings and abbreviations |
| OCR Corruption | Digit substitution, missing spaces |
| Shared Filler | 4 companies sharing "Manufacturing" |
| Minimal Diff | Single character is only distinguishing info |
| Long Noisy | DBA clauses, "FORMERLY" references |
| Unicode Mess | Non-breaking spaces, accented chars |
| Abbrev Explosion | Triple abbreviation stacking |
| Kitchen Sink | All above combined |

Known limitations documented: shared filler words, OCR digit substitution, minimal distinguishing info, embedding false merges, abbreviation explosion. See `docs/knowledge/supplier_clustering_lessons.md` for details.

### `test_human_review.py` — Human Review System (14 tests)

| Test | What it validates |
|------|-------------------|
| `test_find_uncertain_pairs` | Identifies pairs where clustering is uncertain |
| `test_write_review_file` | Writes YAML with review ID, pair IDs, and default decisions |
| `test_load_confirmed_mappings` | Reads human-curated canonical assignments |
| `test_load_confirmed_mappings_missing` | Missing file returns empty dict |
| `test_load_review_decisions` | Reads merge/split/skip decisions from review files |
| `test_load_review_decisions_missing` | Missing file returns empty lists |
| `test_apply_human_overrides_confirmed` | Confirmed mappings merge clusters correctly |
| `test_apply_human_overrides_merge_decision` | Merge decision unifies two clusters |
| `test_apply_human_overrides_split_decision` | Split decision separates a cluster |
| `test_apply_no_overrides` | No override files returns clusters unchanged |
| `test_review_cli_command` | CLI `review` command generates candidates with review ID |
| `test_reviews_cli_command` | CLI `reviews` command lists all review sessions |
| `test_list_reviews` | `list_reviews()` returns review metadata (ID, status, counts) |

### `test_human_loop_e2e.py` — End-to-End Human-in-the-Loop (7 tests)

Simulates the complete human review cycle with ground truth validation.

| Step | Test | What it proves |
|:----:|------|----------------|
| 1 | `test_step1_initial_clustering_has_errors` | Auto-clustering is imperfect (F1=95%, 6 clusters vs expected 5) |
| 2 | `test_step2_review_candidates_generated` | System flags 3 uncertain pairs with similarity scores |
| 3 | `test_step3_human_makes_decisions` | Simulated human correctly decides 1 merge + 2 splits |
| 4 | `test_step4_re_evaluation_improves` | After human review: F1 improves from 95% to 100% |
| 5 | `test_step5_confirmed_mappings_persist` | Confirmed mappings achieve perfect P=100%, R=100% |
| 6 | `test_step6_new_data_triggers_review` | New unknown names flagged, confirmed names left alone |
| 7 | `test_full_build_normalizer_integration` | `build_normalizer()` with `confirmed_path` produces correct lookup |

For a hands-on walkthrough of the human review workflow, see `docs/human_in_the_loop_guide.md`.
