# Human-in-the-Loop Supplier Name Review System

## Table of Contents

- [Problem](#problem)
- [Solution: Two-Stage Pipeline + Human Review](#solution-two-stage-pipeline--human-review)
  - [Stage 1: Automated Clustering](#stage-1-automated-clustering-pipeline-method)
  - [Stage 2: Human Review with Review IDs](#stage-2-human-review-with-review-ids)
  - [Stage 3: Confirmed Mappings](#stage-3-confirmed-mappings)
  - [Priority Order](#priority-order)
- [Workflow](#workflow)
- [Review ID System](#review-id-system)
- [Technical Details](#technical-details)
  - [How Uncertain Pairs Are Found](#how-uncertain-pairs-are-found)
  - [Cleanco Integration](#cleanco-integration)
  - [Expanded Abbreviation Dictionary](#expanded-abbreviation-dictionary)

## Problem

Automated clustering can't solve every case. When it's uncertain:
- **False merges**: "Pacific Steel Mfg" merged with "Pacific Thermal Mfg" (high token overlap)
- **False splits**: "APEX MFG" split from "Apex Manufacturing" (abbreviation mismatch)

Attempting to fix these with tighter/looser thresholds just shifts errors between precision and recall (overfitting).

## Solution: Two-Stage Pipeline + Human Review

### Stage 1: Automated Clustering (Pipeline method)
1. Hybrid v1 runs first for high recall (merge aggressively)
2. Pipeline stage 2 reviews large clusters using TF-IDF + embedding gates
3. Splits pairs where neither signal is confident (max(J, E) < threshold)

### Stage 2: Human Review with Review IDs

Each review session gets a unique timestamp-based ID (e.g., `20260325_013331`). The system writes uncertain pairs to a per-session file:

```
config/review/review_20260325_013331.yaml
```

Each pair within a review also gets a unique ID:

```yaml
review_id: "20260325_013331"
created: "2026-03-25T01:33:31"
status: pending
pairs:
  - pair_id: "20260325_013331_001"
    name_a: "Pacific Steel Manufacturing Inc"
    name_b: "Pacific Thermal Manufacturing Inc"
    tfidf_jaccard: 0.36
    embedding_cosine: 0.76
    current_action: merged
    reason: "Merged but confidence=0.76 < 0.85"
    decision: merged          # current decision (merge/split/skip)
    decided_by: auto          # "auto" or "human"
    decided_at: "2026-03-25T01:33:31"  # when the decision was made
```

Each pair tracks:
- **`decision`**: the current merge/split/skip decision
- **`decided_by`**: `auto` (system default) or `human` (overridden by a reviewer)
- **`decided_at`**: ISO timestamp of when the decision was made/changed

The interactive `decide` command lets you navigate freely (prev/next/goto) and change any decision. Human overrides update `decided_by` to `human` with a new timestamp.

### Stage 3: Confirmed Mappings
Permanent human decisions go in `config/confirmed_mappings.yaml`:

```yaml
mappings:
  - names: ["APEX MFG", "Apex Mfg", "APEX Manufacturing Inc"]
    canonical: "Apex Manufacturing"
```

These override all automated decisions and all review decisions.

### Priority Order
1. `config/confirmed_mappings.yaml` (highest — explicit human assignments)
2. `config/review/*.yaml` (merge/split decisions from all review sessions)
3. Automated pipeline (for names not covered by overrides)

## Workflow

```bash
# 1. Generate review (gets unique ID)
make review

# 2. List reviews and their status
make reviews

# 3. Interactively review a specific session
make decide REVIEW_ID=20260325_013331

# 4. Or review the most recent pending session
make decide

# 5. Apply a specific review's decisions
make ingest REVIEW_ID=20260325_013331

# 6. Or apply all reviews
make ingest

# 7. For permanent overrides, edit config/confirmed_mappings.yaml
```

## Review ID System

- **Review ID format**: `YYYYMMDD_HHMMSS` (timestamp of creation)
- **Pair ID format**: `<review_id>_<sequence>` (e.g., `20260325_013331_001`)
- **File location**: `config/review/review_<id>.yaml`
- **Independence**: Multiple reviews can exist and be worked on separately
- **Aggregation**: `make ingest` reads all review files by default, or a specific one via `REVIEW_ID`

## Technical Details

### How Uncertain Pairs Are Found
Two types checked after clustering:

1. **Within-cluster weak pairs**: For each cluster with 3+ members, check all pairs.
   If max(tfidf_jaccard, embedding_cosine) < 0.85, flag for review.

2. **Cross-cluster high-similarity pairs**: Compare cluster representatives.
   If either tfidf_jaccard >= 0.55 or embedding_cosine >= 0.55, flag as possible
   false split. Candidate suggestions ranked by cosine similarity.

### Cleanco Integration
Legal suffix stripping uses the `cleanco` library which recognizes 203
entity designator categories across 80+ countries (Inc, LLC, GmbH, SA, etc.).

### Expanded Abbreviation Dictionary
30+ industry abbreviations mapped:
Mfg->Manufacturing, Eng->Engineering, Tech->Technology, Sys->Systems,
Svc->Services, Fab->Fabrication, Equip->Equipment, Elec->Electric,
Chem->Chemical, Mech->Mechanical, Auto->Automotive, Aero->Aerospace,
Pharma->Pharmaceutical, and more.
