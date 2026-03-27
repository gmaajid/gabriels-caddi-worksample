# Human-in-the-Loop Pipeline Guide

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Step-by-Step Walkthrough](#step-by-step-walkthrough)
  - [Step 1: Generate a Review](#step-1-generate-a-review)
  - [Step 2: Review Interactively](#step-2-review-interactively)
  - [Step 3: List and Manage Reviews](#step-3-list-and-manage-reviews)
  - [Step 4: Verify Results](#step-4-verify-results)
  - [Step 5: Promote to Confirmed Mappings](#step-5-promote-to-confirmed-mappings)
  - [Step 6: Ingest with a Specific Review](#step-6-ingest-with-a-specific-review)
  - [Step 7: Iterate When New Data Arrives](#step-7-iterate-when-new-data-arrives)
- [Review IDs](#review-ids)
- [How to Decide](#how-to-decide)
- [Changing a Previous Decision](#changing-a-previous-decision)
- [Priority Order](#priority-order)
- [File Reference](#file-reference)
- [Troubleshooting](#troubleshooting)
- [Running the Automated Tests](#running-the-automated-tests)

## Overview

The supplier name normalization pipeline combines automated clustering with human review. Each review session gets a unique ID so reviews can be tracked and worked on independently.

```
make review                    Create a new review (gets unique ID)
  |
  v
make reviews                   List all reviews and their status
  |
  v
make decide REVIEW_ID=xxx      Interactively review that session's pairs
  |
  v
make ingest REVIEW_ID=xxx      Apply that review's decisions
  |
  v
config/confirmed_mappings.yaml Promote permanent mappings here
```

## Prerequisites

```bash
make setup
```

## Step-by-Step Walkthrough

### Step 1: Generate a Review

```bash
make review
```

Output:
```
Found 625 name occurrences (33 unique)
Clustering produced 13 groups

24 uncertain pairs written.
  Review ID: 20260325_013331
  File:      config/review/review_20260325_013331.yaml

Run rag decide 20260325_013331 to review interactively.
```

Each run creates a new file in `config/review/` with a unique timestamp-based ID. Previous reviews are untouched.

### Step 2: Review Interactively

```bash
# Review a specific session
make decide REVIEW_ID=20260325_013331

# Or review the most recent pending session
make decide
```

The tool presents each pair with visual similarity bars, the current decision, who made it, and when:

```
Review: 20260325_013331 (24 pairs: 0 human, 24 auto)
  m=merge  s=split  Enter=skip  p=prev  n=next  g N=goto pair N  q=quit

--- 20260325_013331_001 (1/24) ---
  A: APEX MFG
  B: Apex Fabrication Services
  Jaccard:   [+++-----------------] 0.18
  Embedding: [++++++--------------] 0.34
  System:    merged — Merged but confidence=0.34 < 0.85
  Decision:  merged (auto)
  >
```

After you make a decision, it shows who made it and when:

```
  Decision:  split (human @ 2026-03-25T01:46)
```

### Controls

| Key | Action |
|-----|--------|
| `m` | Merge (same company) |
| `s` | Split (different companies) |
| `Enter` | Skip to next pair |
| `p` | Go to previous pair |
| `n` | Go to next pair |
| `g N` | Jump to pair N (e.g., `g 5`) |
| `q` | Save and quit |

### Changing Previous Decisions

Just navigate back with `p` or `g N` and make a new decision. The tool overwrites the previous one and records the new timestamp. You can tell what you've changed vs what the system decided by the `(auto)` vs `(human @ timestamp)` label.

Decisions save automatically when you quit. Run `make decide` again to pick up where you left off.

### Step 3: List and Manage Reviews

```bash
make reviews
```

Output:
```
                Review Sessions
+-----------------+------------------+---------+---------+---------+-------+
| Review ID       | Created          | Status  | Decided | Pending | Total |
+-----------------+------------------+---------+---------+---------+-------+
| 20260325_013331 | 2026-03-25T01:33 | pending |       2 |      22 |    24 |
| 20260325_091500 | 2026-03-25T09:15 | complete|      10 |       0 |    10 |
+-----------------+------------------+---------+---------+---------+-------+

Use rag decide <review_id> to review a specific session.
```

### Step 4: Verify Results

Check the before/after impact of a review:

```bash
.venv/bin/python -c "
from src.supplier_clustering import ClusterMethod, cluster_names
from src.human_review import apply_human_overrides
from rag.config import CONFIRMED_MAPPINGS_PATH, REVIEW_DIR
import csv

with open('data/demo_suppliers.csv') as f:
    names = [r['supplier_name'] for r in csv.DictReader(f)]

clusters = cluster_names(names, method=ClusterMethod.PIPELINE)
print('BEFORE review:')
for c, members in sorted(clusters.items()):
    print(f'  {c}: {members}')

clusters = apply_human_overrides(clusters,
    confirmed_path=CONFIRMED_MAPPINGS_PATH,
    review_dir=REVIEW_DIR)
print()
print('AFTER review (all reviews applied):')
for c, members in sorted(clusters.items()):
    print(f'  {c}: {members}')
"
```

### Step 5: Promote to Confirmed Mappings

Once you're confident, add permanent overrides to `config/confirmed_mappings.yaml`:

```yaml
mappings:
  - names:
      - "APEX MFG"
      - "Apex Mfg"
      - "APEX Manufacturing Inc"
      - "Apex Manufacturing Inc"
    canonical: "Apex Manufacturing"

  - names:
      - "TitanForge LLC"
      - "TITANFORGE"
      - "Titan Forge Inc"
    canonical: "TitanForge"
```

Confirmed mappings override everything — all reviews and all automation.

### Step 6: Ingest with a Specific Review

```bash
# Apply only a specific review's decisions
make ingest REVIEW_ID=20260325_013331

# Apply all reviews
make ingest
```

### Step 7: Iterate When New Data Arrives

```bash
make review                          # New review ID generated
make decide REVIEW_ID=<new_id>       # Only new uncertain pairs
make ingest REVIEW_ID=<new_id>       # Apply just that review
```

Previous reviews and confirmed mappings are never re-questioned.

## Review IDs

Every review session gets a unique ID based on the timestamp: `YYYYMMDD_HHMMSS`.

Each pair within a review also gets an ID: `<review_id>_<sequence>`, e.g., `20260325_013331_001`.

Review files are stored at:
```
config/review/review_20260325_013331.yaml
config/review/review_20260325_091500.yaml
...
```

This means:
- Multiple reviews can exist simultaneously
- You can work on different reviews at different times
- Reviews don't interfere with each other
- `make ingest` aggregates decisions from all reviews (unless you specify `REVIEW_ID`)

## How to Decide

| Scores | Likely Action | Reasoning |
|--------|---------------|-----------|
| High J + High E | `merge` | Both signals agree — same company |
| Low J + Low E | `split` | Both signals agree — different companies |
| High J + Low E | Check context | Same tokens but different meaning? |
| Low J + High E | Check context | Semantically similar but different tokens? |

Common patterns:
- **Same company, different abbreviation**: `APEX MFG` / `Apex Manufacturing Inc` — merge
- **Same prefix, different business**: `AeroFlow` / `AeroTech` — split
- **Typo variant**: `QuickFab` / `QuikFab` — merge
- **Same industry, different company**: `Pacific Steel Mfg` / `Pacific Thermal Mfg` — split

## Changing a Previous Decision

Three options:

1. **Edit the review YAML directly** — open `config/review/review_<id>.yaml`, change `decision: merge` to `decision: split` (or vice versa), then `make ingest`.

2. **Override with confirmed mappings** — add the correct grouping to `config/confirmed_mappings.yaml`. This takes highest priority and permanently overrides any review decision.

3. **Start a fresh review** — run `make review` to create a new review session. The old one remains but can be ignored.

## Priority Order

The system applies overrides in this order (highest priority first):

1. **`config/confirmed_mappings.yaml`** — permanent human-curated assignments
2. **`config/review/*.yaml`** — merge/split decisions from all review sessions
3. **Automated pipeline** — for names not covered by any override

## File Reference

| File | Purpose | Who edits it |
|------|---------|:------------:|
| `config/confirmed_mappings.yaml` | Permanent canonical name assignments | Human |
| `config/review/review_<id>.yaml` | Per-session review with pair-level IDs | System generates, human reviews via `make decide` |
| `src/supplier_clustering.py` | Clustering engine | Developer |
| `src/human_review.py` | Review system (IDs, file management, overrides) | Developer |
| `rag/cli.py` | CLI commands (`review`, `reviews`, `decide`, `ingest`) | Developer |
| `rag/config.py` | Paths to all config/data directories | Developer |

## Troubleshooting

**"No uncertain pairs found"** — The clustering is fully confident. Use `data/demo_suppliers.csv` for testing — it has 33 messy names that produce 24 uncertain pairs.

**"No pending reviews"** — All review sessions are complete. Run `make review` to create a new one from current data.

**Review not found** — Check the ID with `make reviews`. IDs are timestamp-based: `YYYYMMDD_HHMMSS`.

**Wrong cluster after review** — Either edit the review YAML directly, or add the correct mapping to `config/confirmed_mappings.yaml` (overrides everything).

**Want to ignore an old review** — Delete its file from `config/review/`. Only files matching `review_*.yaml` are read.

## Running the Automated Tests

```bash
# Human-in-the-loop e2e tests
.venv/bin/pytest src/tests/test_human_loop_e2e.py -v -s

# All tests
make test

# With coverage
make test-cov
```

The e2e test (`src/tests/test_human_loop_e2e.py`) simulates the complete cycle:
1. Initial clustering has errors (F1=95%, 6 clusters instead of 5)
2. System flags 3 uncertain pairs with similarity scores
3. Simulated human makes correct merge/split decisions
4. Re-evaluation achieves F1=100%
5. Confirmed mappings persist across future runs
6. New data triggers review for only unknown names
