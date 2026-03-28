# Phase 1: AI-Assisted Procurement System — Design Specification

## Table of Contents

- [1. Overview](#1-overview)
- [2. Goals and Non-Goals](#2-goals-and-non-goals)
- [3. Data Architecture](#3-data-architecture)
  - [3.1 File Layout](#31-file-layout)
  - [3.2 M&A Registry Schema](#32-ma-registry-schema)
  - [3.3 Test Scenario Schema](#33-test-scenario-schema)
  - [3.4 Demo Data CSVs](#34-demo-data-csvs)
- [4. Temporal Name Chain Resolution](#4-temporal-name-chain-resolution)
  - [4.1 Chain Structure](#41-chain-structure)
  - [4.2 Three-Stage Resolution Pipeline](#42-three-stage-resolution-pipeline)
  - [4.3 Chain Validation and Error Detection](#43-chain-validation-and-error-detection)
  - [4.4 Human Escalation Conditions](#44-human-escalation-conditions)
- [5. CLI Commands](#5-cli-commands)
  - [5.1 M&A Registry Management](#51-ma-registry-management)
  - [5.2 Demo Data Generation and Benchmarking](#52-demo-data-generation-and-benchmarking)
- [6. Difficulty Tier System](#6-difficulty-tier-system)
  - [6.1 Tier Definitions](#61-tier-definitions)
  - [6.2 Precision and Recall by Tier](#62-precision-and-recall-by-tier)
- [7. Web Visualization](#7-web-visualization)
  - [7.1 Graph Layout](#71-graph-layout)
  - [7.2 Interactions](#72-interactions)
  - [7.3 Alerts Panel](#73-alerts-panel)
- [8. Integration with Existing Systems](#8-integration-with-existing-systems)
  - [8.1 Clustering Pipeline Integration](#81-clustering-pipeline-integration)
  - [8.2 RAG Integration](#82-rag-integration)
  - [8.3 Confirmed Mappings Interaction](#83-confirmed-mappings-interaction)
- [9. Entity ID Scheme](#9-entity-id-scheme)
  - [9.1 ID Format](#91-id-format)
  - [9.2 Division Addressing](#92-division-addressing)
  - [9.3 CLI Usage](#93-cli-usage)
- [10. Deployment and Portability](#10-deployment-and-portability)
- [11. Phased Implementation Plan](#11-phased-implementation-plan)
- [12. Testing Strategy](#12-testing-strategy)
- [13. Demo Walkthrough Script](#13-demo-walkthrough-script)

---

## 1. Overview

Phase 1 extends the existing supplier name clustering system into a full **AI-assisted procurement preprocessing pipeline** capable of handling data inconsistencies that go beyond simple name variants — including mergers, acquisitions, rebrands, and corporate restructuring.

The system automatically resolves supplier names by traversing a temporal chain of corporate events (M&A registry), only escalating to humans when the chain is broken, ambiguous, or temporally inconsistent.

A web-based visualization tool provides an interactive graph of supplier name relationships, confidence scores, and chain health.

**Context:** This is a working prototype for a 30-60 minute demo interview with CADDi. The system processes Hoth Industries' supply chain data (air handling/cooling products for data centers) and demonstrates how CADDi Drawer could solve procurement data quality issues at the Manufacturing/Procurement stage of the customer workflow.

---

## 2. Goals and Non-Goals

### Goals

- Automatically resolve supplier names across M&A events without human intervention for valid chains
- Detect and surface broken chains, cycles, temporal conflicts, and ambiguous forks to humans
- Generate synthetic demo data with controlled difficulty levels for benchmarking
- Measure precision/recall by difficulty tier to demonstrate system limits transparently
- Provide a web-based interactive graph visualization of name relationships
- Add M&A event management via `caddi-cli`

### Non-Goals

- Processing unstructured documents (PDFs, scanned invoices) — future phase
- Supporting data formats beyond the 3 Hoth CSV schemas — future phase
- Real-time streaming ingestion — batch processing only
- External M&A data feeds (SEC filings, news) — manual registry for now

---

## 3. Data Architecture

### 3.1 File Layout

```
data/
  Copy of supplier_orders.csv            # Real Hoth data (500 rows, untouched)
  Copy of quality_inspections.csv        # Real Hoth data (200 rows, untouched)
  Copy of rfq_responses.csv             # Real Hoth data (92 rows, untouched)
  demo/                                  # Synthetic scenario data
    demo_orders.csv                      # Same schema as real, messy names
    demo_inspections.csv                 # Same schema as real
    demo_rfq.csv                         # Same schema as real

config/
  confirmed_mappings.yaml                # Existing — name -> canonical (highest priority)
  ma_registry.yaml                       # NEW — M&A events with dates and name chains
  test_scenarios.yaml                    # NEW — ground truth + difficulty tiers
  reviewer.yaml                          # Existing — reviewer identity
```

### 3.2 M&A Registry Schema

The M&A registry uses **entity IDs** (short hashes with friendly names) rather than text strings as keys. This prevents key-matching failures from typos and keeps the YAML compact.

```yaml
# config/ma_registry.yaml

# --- Entity Registry ---
# Every company, division, or post-M&A entity gets a unique ID.
# IDs are auto-generated short hashes. Friendly names are for human use.
# Divisions use <parent_id>:<child_id> addressing for guaranteed uniqueness.

entities:
  # --- Root companies ---
  - id: e7f3a2
    name: "Apex Manufacturing"
    friendly: "apex-mfg"
    divisions: [e7f3a2:b1c4d8, e7f3a2:d9e5f1, e7f3a2:a3b7c2]

  - id: c3d4e5
    name: "QuickFab Industries"
    friendly: "quickfab"

  - id: f8a1b9
    name: "Precision Thermal Co"
    friendly: "precision-thermal"

  - id: a2c6d3
    name: "Stellar Metalworks"
    friendly: "stellar"

  - id: d4e8f2
    name: "TitanForge LLC"
    friendly: "titanforge"

  - id: c9a3b7
    name: "AeroFlow Systems"
    friendly: "aeroflow"

  # --- Divisions (operationally independent, linked to parent) ---
  - id: b1c4d8
    name: "Bright Star Foundrys"
    friendly: "bright-star"
    parent: e7f3a2                        # Apex Manufacturing

  - id: d9e5f1
    name: "Juniper Racing Parts"
    friendly: "juniper-racing"
    parent: e7f3a2

  - id: a3b7c2
    name: "Knight Fastener Fabrication Services"
    friendly: "knight-fastener"
    parent: e7f3a2


# --- M&A Events ---
# All references use entity IDs, not text strings.

events:
  - id: ma-8f2a1b
    type: acquisition                     # acquisition | merger | rebrand | restructure
    date: "2024-07-15"
    acquirer: e7f3a2                      # Apex Manufacturing (entity ID)
    acquired: c3d4e5                      # QuickFab Industries (entity ID)
    resulting_names:
      - name: "Apex-QuickFab Industries"
        first_seen: "2024-08-01"
      - name: "AQF Holdings"
        first_seen: "2024-09-15"
      - name: "Apex Manufacturing - QuickFab Division"
        first_seen: "2024-08-01"
    notes: "QuickFab absorbed into Apex's supply division after Q2 earnings"

  - id: ma-c4d5e6
    type: rebrand
    date: "2025-01-01"
    acquirer: f8a1b9                      # reuses Precision Thermal's entity
    acquired: f8a1b9                      # same entity, new name
    resulting_names:
      - name: "Zenith Thermal Solutions"
        first_seen: "2025-01-15"
      - name: "Zenith Thermal"
        first_seen: "2025-02-01"
    notes: "Full rebrand, zero token overlap with original name"

  - id: ma-a1b2c3
    type: merger
    date: "2023-06-01"
    acquirer: a2c6d3                      # Stellar Metalworks (surviving entity ID)
    acquired: d4e8f2                      # TitanForge LLC
    co_merged: [a2c6d3, d4e8f2]           # entity IDs of all parties
    resulting_names:
      - name: "StellarForge Industries"
        first_seen: "2023-07-01"
      - name: "SF Industries"
        first_seen: "2023-08-01"
    notes: "Equal merger of Stellar Metalworks and TitanForge"

  - id: ma-e5f6a7
    type: restructure
    date: "2024-01-15"
    acquirer: c9a3b7                      # AeroFlow Systems (same entity)
    acquired: c9a3b7
    resulting_names:
      - name: "AeroFlow Technologies"
        first_seen: "2024-02-01"
      - name: "AeroFlow Tech"
        first_seen: "2024-03-01"
    notes: "Corporate restructuring, same ownership"
```

**Design decisions:**
- **Entity IDs are short hashes** (6 hex chars), auto-generated by `caddi-cli ma add`
- **Friendly names** are human-readable slugs for CLI convenience (`apex-mfg` instead of `e7f3a2`)
- **Division addressing** uses `<parent_id>:<child_id>` pairs for guaranteed uniqueness
- **Divisions are operationally independent** — they keep their own canonical name for POs/RFQs but the parent relationship is tracked for aggregate analytics
- **All M&A event references use entity IDs**, not text — if a company name has a typo fix, it changes in one place
- `acquirer` is always the surviving/resulting entity — the canonical name chain root
- `acquired` is the entity being absorbed, renamed, or transformed
- `co_merged` supports multi-party mergers using entity ID lists
- `resulting_names` with `first_seen` dates allow the system to validate temporal consistency
- `type` is informational — the resolution logic treats all types the same (chain traversal)

### 3.3 Test Scenario Schema

Each scenario defines a single name resolution test case with known ground truth and a difficulty tier.

```yaml
# config/test_scenarios.yaml

metadata:
  generated: "2026-03-27"
  description: "Ground truth for entity resolution benchmarking"

scenarios:
  # --- Tier 1: Easy (abbreviation, case, suffix) ---
  - id: SC-001
    difficulty: 1
    category: abbreviation
    input_name: "APEX MFG"
    expected_canonical: "Apex Manufacturing"
    requires_ma_registry: false
    description: "Standard abbreviation expansion"

  - id: SC-002
    difficulty: 1
    category: case_variation
    input_name: "apex manufacturing inc"
    expected_canonical: "Apex Manufacturing"
    requires_ma_registry: false
    description: "Lowercase with legal suffix"

  # --- Tier 2: Medium (typos, partial overlap, post-restructure) ---
  - id: SC-010
    difficulty: 2
    category: typo
    input_name: "Quik-Fab Industries"
    expected_canonical: "QuickFab Industries"
    requires_ma_registry: false
    description: "Misspelling with hyphen insertion"

  - id: SC-011
    difficulty: 2
    category: restructure
    input_name: "AeroFlow Technologies"
    expected_canonical: "AeroFlow Systems"
    requires_ma_registry: true
    ma_event: "MA-004"
    description: "Post-restructure name, high token overlap"

  # --- Tier 3: Hard (M&A with partial token overlap) ---
  - id: SC-020
    difficulty: 3
    category: post_acquisition
    input_name: "Apex-QuickFab Industries"
    expected_canonical: "Apex Manufacturing"
    requires_ma_registry: true
    ma_event: "MA-001"
    description: "Compound name from acquisition, contains both parent tokens"

  - id: SC-021
    difficulty: 3
    category: post_merger
    input_name: "StellarForge Industries"
    expected_canonical: "Stellar Metalworks"
    requires_ma_registry: true
    ma_event: "MA-003"
    also_resolves_to: "TitanForge LLC"
    description: "Merger product — resolves to both parents"

  # --- Tier 4: Adversarial (zero overlap, requires M&A registry) ---
  - id: SC-030
    difficulty: 4
    category: full_rebrand
    input_name: "Zenith Thermal Solutions"
    expected_canonical: "Precision Thermal Co"
    requires_ma_registry: true
    ma_event: "MA-002"
    description: "Complete rebrand, zero token/embedding similarity"

  - id: SC-031
    difficulty: 4
    category: acronym_rebrand
    input_name: "AQF Holdings"
    expected_canonical: "Apex Manufacturing"
    requires_ma_registry: true
    ma_event: "MA-001"
    description: "Acronym of merged entity, no direct token match"
```

**Key fields:**
- `requires_ma_registry`: explicitly marks whether clustering alone can solve it
- `ma_event`: links to the M&A event ID that enables resolution
- `also_resolves_to`: for mergers where multiple parent entities are valid ancestors
- `category`: groups scenarios for per-category precision/recall reporting

### 3.4 Demo Data CSVs

Generated by `caddi-cli demo generate` from the M&A registry and test scenarios. The generator:

1. Reads `ma_registry.yaml` for corporate events
2. Reads `test_scenarios.yaml` for name variants and difficulty tiers
3. Creates synthetic orders, inspections, and RFQs using the same column schemas as the real Hoth data
4. Assigns order dates that are temporally consistent with M&A event dates
5. Uses the same part numbers and part descriptions as real data (to make cross-dataset joins work)

---

## 4. Temporal Name Chain Resolution

### 4.1 Chain Structure

The M&A registry defines a **directed acyclic graph (DAG)** of corporate identity over time. Each node is a company name at a point in time. Each edge is an M&A event.

```
Example chain for MA-001 (acquisition) + MA-001 names:

    QuickFab Industries                 Apex Manufacturing
         │ (acquired 2024-07-15)              │ (acquirer)
         ▼                                    │
    ┌────────────────────────────────────┐    │
    │  MA-001: Acquisition 2024-07-15   │◄───┘
    └────┬──────────┬───────────────────┘
         │          │
         ▼          ▼
  Apex-QuickFab   AQF Holdings    Apex Manufacturing -
  Industries      (2024-09-15)    QuickFab Division
  (2024-08-01)                    (2024-08-01)
```

**Resolution rule:** Any `resulting_name` from an M&A event resolves to the `acquirer` as its canonical ancestor. For mergers, it resolves to all `co_merged` parties as well.

**Temporal rule:** A `resulting_name` is only valid for orders dated **on or after** the event date. If a resulting name appears on an order before the event date, this is a temporal conflict (see 4.4).

### 4.2 Three-Stage Resolution Pipeline

```
Input: (supplier_name, order_date)
         │
         ▼
┌──────────────────────────────────┐
│  Stage 1: Clustering             │
│  Existing hybrid pipeline        │
│  Handles: abbreviations, typos,  │
│  case, legal suffixes            │
│  Resolves: Tier 1-2              │
│                                  │
│  Output: canonical OR unresolved │
│  Confidence: 0.0 - 1.0          │
└──────────┬───────────────────────┘
           │ if unresolved (confidence < threshold)
           ▼
┌──────────────────────────────────┐
│  Stage 2: M&A Chain Traversal    │
│  Search ma_registry.yaml         │
│  Match input against:            │
│    - resulting_names              │
│    - acquired entities            │
│  Apply temporal filter:           │
│    event.date <= order_date       │
│  Traverse chain to root ancestor │
│                                  │
│  Output: canonical OR unresolved │
│  Confidence: 1.0 (explicit link) │
│  Source: "ma_registry"           │
└──────────┬───────────────────────┘
           │ if unresolved
           ▼
┌──────────────────────────────────┐
│  Stage 3: Validation + Escalate  │
│  Check for chain errors:         │
│    - Broken chains               │
│    - Cycles                      │
│    - Temporal conflicts           │
│    - Ambiguous forks             │
│    - Orphaned entities           │
│  Generate actionable alerts      │
│  Flag for human review           │
│                                  │
│  Output: alert report            │
└──────────────────────────────────┘
```

**Stage 1 and Stage 2 can both contribute.** If Stage 1 produces a low-confidence match (e.g., 0.6) and Stage 2 finds an M&A chain, Stage 2 wins (confidence 1.0). If Stage 1 produces a high-confidence match (e.g., 0.95) and no M&A event exists, Stage 1's result stands.

### 4.3 Chain Validation and Error Detection

The system validates the M&A registry on every load and before every resolution run:

**Cycle detection:** Depth-first traversal of the acquirer→acquired graph. If any node is visited twice in a single path, the cycle is reported with the full loop path.

**Broken chain detection:** When a name resolves partway through a chain but can't reach the root canonical. This happens when:
- Downstream evidence (a `resulting_name`) references an `acquired` entity
- But the `acquired` entity's own ancestry is incomplete
- The system knows the gap exists because it can see nodes on both sides

Example:
```
Known: AQF Holdings ──(MA-001)──▶ Apex Manufacturing
Known: QuickFab Industries existed before MA-001
Missing: No event links QuickFab Industries to the chain

Alert: "Broken chain: QuickFab Industries is listed as 'acquired' in MA-001
        but has no prior history. Was there an earlier M&A event?"
```

**Temporal conflict detection:** An order uses a `resulting_name` before the M&A event date:
```
Alert: "Temporal conflict: Order PO-2024-292 (dated 2024-03-15) uses name
        'AQF Holdings' but MA-001 (acquisition) occurred 2024-07-15.
        This name should not exist before that date."
```

**Ambiguous fork detection:** A name could resolve to multiple unrelated canonical entities through different M&A paths:
```
Alert: "Ambiguous resolution: 'Apex Industries' matches:
        - Apex Manufacturing (via clustering, confidence 0.72)
        - Apex Fabrication (via clustering, confidence 0.68)
        No M&A event disambiguates. Human review required."
```

**Orphaned entity detection:** An M&A event references an entity that doesn't appear in any dataset or other M&A event:
```
Alert: "Orphaned entity: MA-003 references 'TitanForge LLC' as co_merged
        but this name appears in 0 orders, 0 inspections, 0 RFQs,
        and 0 other M&A events."
```

### 4.4 Human Escalation Conditions

Humans are only involved when the automated system cannot resolve with certainty. Each escalation is an **actionable alert**, not a generic "needs review" flag.

| Condition | Detection Method | Alert Content | Expected Human Action |
|-----------|-----------------|---------------|----------------------|
| Broken chain | Chain traversal hits dead end but downstream evidence exists | Shows both sides of gap, suggests missing M&A event | Add missing M&A event to registry |
| Cycle | DFS finds back-edge | Shows full cycle path | Correct the registry (wrong acquirer/acquired direction) |
| Temporal conflict | `order_date < event.date` for a resulting_name | Shows order, name, event, and dates | Verify order date or event date is correct |
| Ambiguous fork | Multiple canonical candidates with similar confidence | Shows candidates ranked by score | Select correct canonical or add M&A event to disambiguate |
| Orphaned entity | Entity in M&A registry has zero occurrences in all data | Shows the event and missing entity | Verify entity name spelling or remove from registry |

---

## 5. CLI Commands

### 5.1 M&A Registry Management

```bash
# List all M&A events
caddi-cli ma list

# Output:
# M&A Registry
# ┌────────┬─────────────┬────────────┬───────────────────────┬───────────────────────┬──────────┐
# │ ID     │ Type        │ Date       │ Acquirer              │ Acquired              │ Names    │
# ├────────┼─────────────┼────────────┼───────────────────────┼───────────────────────┼──────────┤
# │ MA-001 │ acquisition │ 2024-07-15 │ Apex Manufacturing    │ QuickFab Industries   │ 3        │
# │ MA-002 │ rebrand     │ 2025-01-01 │ Zenith Thermal Sol... │ Precision Thermal Co  │ 2        │
# └────────┴─────────────┴────────────┴───────────────────────┴───────────────────────┴──────────┘


# Add an M&A event interactively
caddi-cli ma add

# Prompts:
#   Event type (acquisition/merger/rebrand/restructure): acquisition
#   Date (YYYY-MM-DD): 2024-07-15
#   Acquirer (surviving entity): Apex Manufacturing
#   Acquired entity: QuickFab Industries
#   Resulting name 1 (or Enter to finish): Apex-QuickFab Industries
#   Resulting name 2 (or Enter to finish): AQF Holdings
#   Resulting name 3 (or Enter to finish):
#   Notes (optional): QuickFab absorbed into Apex
#
#   Created: MA-005


# Add non-interactively (for scripting)
caddi-cli ma add \
  --type acquisition \
  --date 2024-07-15 \
  --acquirer "Apex Manufacturing" \
  --acquired "QuickFab Industries" \
  --resulting-name "Apex-QuickFab Industries" \
  --resulting-name "AQF Holdings" \
  --notes "QuickFab absorbed into Apex"


# Show details of a specific event
caddi-cli ma show MA-001


# Remove an M&A event
caddi-cli ma remove MA-001
#   Remove MA-001 (Apex Manufacturing acquired QuickFab Industries)? (y/N): y
#   Removed.


# Validate the registry (check for cycles, orphans, conflicts)
caddi-cli ma validate
#   Checking 4 events...
#   OK: No cycles detected
#   OK: No orphaned entities
#   WARNING: Temporal conflict in MA-002 (see alerts)
#   1 warning, 0 errors
```

### 5.2 Demo Data Generation and Benchmarking

```bash
# Generate synthetic demo CSVs from M&A registry + test scenarios
caddi-cli demo generate
#   Reading ma_registry.yaml (4 events)
#   Reading test_scenarios.yaml (30 scenarios)
#   Generated:
#     data/demo/demo_orders.csv (120 rows)
#     data/demo/demo_inspections.csv (48 rows)
#     data/demo/demo_rfq.csv (36 rows)


# Run the full resolution pipeline on demo data, report metrics
caddi-cli demo run
#   Resolving 120 orders against 30 test scenarios...
#
#   Entity Resolution Results
#   ┌────────────┬───────┬──────────┬────────┬────────┬──────┐
#   │ Difficulty │ Total │ Resolved │ Prec.  │ Recall │  F1  │
#   ├────────────┼───────┼──────────┼────────┼────────┼──────┤
#   │ 1 (easy)   │    12 │   12/12  │ 100.0% │ 100.0% │ 1.00 │
#   │ 2 (medium) │     8 │    7/8   │ 100.0% │  87.5% │ 0.93 │
#   │ 3 (hard)   │     6 │    5/6   │  83.3% │  83.3% │ 0.83 │
#   │ 4 (advers) │     4 │    1/4   │ 100.0% │  25.0% │ 0.40 │
#   ├────────────┼───────┼──────────┼────────┼────────┼──────┤
#   │ Overall    │    30 │   25/30  │  96.0% │  83.3% │ 0.89 │
#   └────────────┴───────┴──────────┴────────┴────────┴──────┘
#
#   Alerts (5 items):
#     [BROKEN_CHAIN] "AQF Holdings" — missing link to QuickFab Industries
#     [TEMPORAL]     PO-DEMO-042 uses "Zenith Thermal" before rebrand date
#     ...


# Show the last run's report (without re-running)
caddi-cli demo report

# Show report for a specific category
caddi-cli demo report --category post_acquisition

# Show report for a specific difficulty tier
caddi-cli demo report --tier 3
```

---

## 6. Difficulty Tier System

### 6.1 Tier Definitions

| Tier | Name | Signal Available | Resolution Method | Example |
|------|------|-----------------|-------------------|---------|
| 1 | Easy | High token overlap + high embedding similarity | Clustering alone | "APEX MFG" -> "Apex Manufacturing" |
| 2 | Medium | Partial token overlap OR moderate embedding similarity | Clustering (may need lower threshold) or simple M&A lookup | "Quik-Fab Industries" (typo), "AeroFlow Technologies" (restructure) |
| 3 | Hard | Low token overlap but M&A chain connects them | M&A registry traversal (1+ hops) | "Apex-QuickFab Industries", "StellarForge Industries" |
| 4 | Adversarial | Zero token overlap, zero embedding similarity | M&A registry only (multi-hop or full rebrand) | "AQF Holdings", "Zenith Thermal Solutions" |

### 6.2 Precision and Recall by Tier

**Precision** = (correct resolutions) / (all resolutions attempted)
**Recall** = (correct resolutions) / (all scenarios in that tier)

Expected performance profile:
- **Tier 1-2:** Clustering handles these. P/R should be >95%.
- **Tier 3:** M&A registry handles these. P/R depends on registry completeness. With complete registry: 100%. With gaps: drops proportionally.
- **Tier 4:** M&A registry is the **only** path. Without the registry entry, recall = 0%. This is by design — it demonstrates the system's transparency about what it can and cannot solve.

**Demo narrative:** "Tier 4 scores tell you exactly where your M&A registry has gaps. A score of 40% recall on adversarial cases means 60% of your corporate events aren't recorded yet."

---

## 7. Web Visualization

A reactive single-page application that renders the supplier name relationship graph.

### 7.1 Graph Layout

**Nodes:**
- **Canonical names** (large, colored by supplier): central hub nodes
- **Raw variants** (small): clustered around their canonical
- **M&A resulting names** (medium, distinct shape): connected via M&A event edges
- **Unresolved names** (red border, pulsing): names that failed resolution

**Edges:**
- **Clustering edges**: width proportional to confidence score, colored green (>0.85), yellow (0.55-0.85), red (<0.55)
- **M&A edges**: dashed line, labeled with event ID and date, always confidence 1.0
- **Broken chain edges**: dotted red line with "?" label

### 7.2 Interactions

- **Hover**: Show edge confidence scores (Jaccard, Embedding, Combined), M&A event details
- **Click node**: Highlight all connected edges, show detail panel with occurrence count, date range, source datasets
- **Click edge**: Show the resolution path (which stage resolved it, what scores)
- **Filter**: By difficulty tier, by M&A event, by confidence range, by alert type
- **Timeline slider**: Scrub through time to see how the graph changes as M&A events take effect
- **Search**: Type a name, highlights the node and its ancestry chain

### 7.3 Alerts Panel

A sidebar that lists all validation alerts from the last run:
- Grouped by severity (error, warning, info)
- Clicking an alert highlights the relevant nodes/edges in the graph
- Shows recommended action for each alert type

---

## 8. Integration with Existing Systems

### 8.1 Clustering Pipeline Integration

The M&A resolver is a **new stage** inserted into the existing pipeline, not a replacement:

```python
def resolve_supplier(name: str, order_date: str) -> ResolutionResult:
    # Stage 1: existing clustering
    cluster_result = cluster_names([name], method=ClusterMethod.PIPELINE)
    if cluster_result.confidence >= 0.85:
        return ResolutionResult(
            canonical=cluster_result.canonical,
            confidence=cluster_result.confidence,
            source="clustering",
            stage=1,
        )

    # Stage 2: M&A chain traversal
    ma_result = ma_resolver.resolve(name, order_date)
    if ma_result.resolved:
        return ResolutionResult(
            canonical=ma_result.canonical,
            confidence=1.0,
            source="ma_registry",
            stage=2,
            ma_event=ma_result.event_id,
            chain=ma_result.chain_path,
        )

    # Stage 3: validate and escalate
    alerts = validator.check(name, order_date, cluster_result, ma_result)
    return ResolutionResult(
        canonical=None,
        confidence=0.0,
        source="unresolved",
        stage=3,
        alerts=alerts,
    )
```

### 8.2 RAG Integration

M&A events are ingested into the RAG as knowledge documents so they're queryable:
- `caddi-cli ingest` includes M&A registry alongside CSVs and knowledge docs
- Queries like "what happened to QuickFab?" return the M&A event details
- The RAG context includes chain information for Claude to synthesize answers

### 8.3 Confirmed Mappings Interaction

Priority order (unchanged, M&A inserted):
1. `confirmed_mappings.yaml` — always wins (human override)
2. M&A registry chain resolution — date-aware corporate events
3. Review file decisions — human merge/split from review sessions
4. Automated clustering — fallback

If a confirmed mapping conflicts with an M&A event, the confirmed mapping wins and a warning is logged.

---

## 9. Entity ID Scheme

### 9.1 ID Format

Every entity gets two identifiers:
- **`id`**: 6-character hex hash, auto-generated from `hashlib.sha256(name + timestamp)[:6]`
- **`friendly`**: human-readable slug, auto-generated from name (`"Apex Manufacturing"` -> `"apex-mfg"`), editable

IDs are immutable once created. Friendly names can be changed without breaking references.

### 9.2 Division Addressing

Divisions use composite keys: `<parent_id>:<child_id>`

```
e7f3a2              → Apex Manufacturing (root entity)
e7f3a2:b1c4d8       → Bright Star Foundrys (Apex division)
e7f3a2:d9e5f1       → Juniper Racing Parts (Apex division)
```

This guarantees uniqueness even if two parents have divisions with colliding short hashes (unlikely but handled). The parent entity stores its division list (`divisions: [e7f3a2:b1c4d8, ...]`), and each division stores its parent (`parent: e7f3a2`).

**Division resolution behavior:**
- POs and RFQs referencing "Bright Star Foundrys" resolve to canonical **"Bright Star Foundrys"** (not Apex)
- The parent link is metadata for aggregate queries ("total Apex family spend")
- `caddi-cli mappings` shows: `Bright Star Foundrys [division of Apex Manufacturing]`
- The web graph renders division edges as thin solid lines labeled "division of"

### 9.3 CLI Usage

Both ID formats work interchangeably:
```bash
caddi-cli ma show e7f3a2                    # by hash
caddi-cli ma show apex-mfg                  # by friendly name
caddi-cli ma show e7f3a2:b1c4d8             # division by hash pair
caddi-cli ma show apex-mfg:bright-star      # division by friendly pair
```

---

## 10. Deployment and Portability

The entire system must run from a single `docker build && docker run` with no external dependencies beyond Claude API (optional).

### 10.1 Docker Image

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[dev]" && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
EXPOSE 8095
ENTRYPOINT ["./caddi-cli"]
```

Key points:
- **Embedding model pre-downloaded** at build time (no internet needed at runtime)
- **ChromaDB is in-process** (no external database)
- **Web visualization served** via built-in Python HTTP server on port 8095
- **ANTHROPIC_API_KEY** is optional — RAG queries work without it (raw mode)

### 10.2 Interviewer Quick Start

```bash
# Clone and run (2 commands)
git clone https://github.com/gmaajid/gabriels-caddi-worksample.git
cd gabriels-caddi-worksample

# Option A: Docker (no Python needed)
docker build -t caddi-demo .
docker run -it -p 8095:8095 caddi-demo demo run

# Option B: Local (Python 3.12+)
make setup
./caddi-cli ingest
./caddi-cli demo run
./caddi-cli viz              # opens browser to localhost:8095
```

### 10.3 What's in the Image

Everything needed to rebuild:
- Source code (`rag/`, `src/`, `caddi-cli`)
- Data (`data/*.csv`, `data/demo/`)
- Config (`config/`)
- Docs (`docs/`)
- Tests (`rag/tests/`, `src/tests/`)
- Web app (`web/`)
- Pre-downloaded embedding model (cached in image layer)

What's NOT in the image:
- `.venv/` (rebuilt by pip install)
- `data/chroma_db/` (rebuilt by `caddi-cli ingest`)
- `.env` (API key passed via `-e` flag or not needed)

---

## 11. Phased Implementation Plan

### Phase 1a: M&A Registry + CLI (foundation)

**Deliverables:**
- `config/ma_registry.yaml` schema and loader
- `src/ma_registry.py` — CRUD operations, chain traversal, validation
- `caddi-cli ma` subcommand group (list, add, show, remove, validate)
- Unit tests for registry operations
- Cycle detection, orphan detection, temporal conflict detection

**Dependencies:** None (standalone module)

### Phase 1b: Demo Data Generator (testing infrastructure)

**Deliverables:**
- `config/test_scenarios.yaml` schema and loader
- `src/demo_generator.py` — creates synthetic CSVs from M&A events + scenarios
- Name corruption functions (abbreviation, typo, OCR, case, M&A rename)
- `caddi-cli demo generate` command
- Difficulty tier tagging

**Dependencies:** Phase 1a (needs M&A registry)

### Phase 1c: M&A-Aware Resolution Pipeline (core logic)

**Deliverables:**
- `src/ma_resolver.py` — Stage 2 resolver with date-aware chain traversal
- `src/chain_validator.py` — broken chain, cycle, temporal conflict, ambiguous fork, orphan detection
- Integration into existing `resolve_supplier()` pipeline
- Edge scores include M&A source attribution
- Alert generation with recommended actions

**Dependencies:** Phase 1a (M&A registry), existing clustering pipeline

### Phase 1d: Precision/Recall Benchmarking (measurement)

**Deliverables:**
- `src/benchmark.py` — evaluate pipeline against ground truth scenarios
- `caddi-cli demo run` — execute benchmarks
- `caddi-cli demo report` — formatted output by tier, category, event
- Metrics: precision, recall, F1 by difficulty tier and category

**Dependencies:** Phase 1b (demo data), Phase 1c (resolver)

### Phase 1e: Web Visualization (demo piece)

**Deliverables:**
- `web/` directory with single-page reactive app
- Force-directed graph layout with D3.js or similar
- Node/edge rendering with confidence score visualization
- Timeline slider for temporal M&A exploration
- Alerts panel with click-to-highlight
- `caddi-cli viz` command to launch local server

**Dependencies:** Phase 1c (resolver output), Phase 1d (benchmark results)

### Phase 1f: Demo Polish (interview readiness)

**Deliverables:**
- Pre-built M&A registry with 4-6 events spanning all difficulty tiers
- Pre-generated demo data
- Walkthrough script for 30-minute demo
- Documentation updates (README, guides)

**Dependencies:** All previous phases

---

## 12. Testing Strategy

### Unit Tests

| Module | Tests | Coverage Target |
|--------|-------|----------------|
| `src/ma_registry.py` | CRUD, chain traversal, cycle detection, temporal validation | 95% |
| `src/ma_resolver.py` | Resolution by stage, date filtering, confidence scoring | 95% |
| `src/chain_validator.py` | Each error condition (broken chain, cycle, temporal, ambiguous, orphan) | 100% |
| `src/demo_generator.py` | CSV generation, name corruption, temporal consistency | 90% |
| `src/benchmark.py` | Metric calculation, tier grouping, category grouping | 95% |

### Integration Tests

- Full pipeline: demo data → resolution → benchmark → verify metrics match expected
- M&A registry changes → re-resolution → verify results change accordingly
- Confirmed mapping overrides M&A → verify priority order

### Adversarial Tests

- Cycle in M&A registry → detected, reported, not infinite loop
- 100+ M&A events → performance remains acceptable
- Name that matches multiple M&A chains → ambiguous fork detected
- Order date exactly on M&A event date → edge case handled consistently

---

## 13. Demo Walkthrough Script

**Target: 30-minute interview demo for Hoth Industries / CADDi**

1. **Setup (2 min):** Show project structure, explain the 3 CSV datasets, run `caddi-cli status`

2. **Problem statement (3 min):** Show raw data — "APEX MFG", "Apex Manufacturing Inc", "Apex Mfg" are the same company. Run `caddi-cli mappings` to show the clustering solved this.

3. **But what about M&A? (3 min):** "What if QuickFab gets acquired by Apex in July 2024? Orders after that date show up as 'Apex-QuickFab Industries' or 'AQF Holdings'. The clustering can't solve this — zero token overlap."

4. **M&A Registry (3 min):** Run `caddi-cli ma list`, show the events. Run `caddi-cli ma add` to add a new event live.

5. **Demo data (2 min):** Run `caddi-cli demo generate`, show the synthetic CSVs with messy names tied to M&A events.

6. **Resolution pipeline (5 min):** Run `caddi-cli demo run`. Walk through the results by difficulty tier. "Tier 1-2: clustering handles it. Tier 3: M&A registry resolves it. Tier 4: only the registry can — and it does."

7. **Broken chain detection (3 min):** Remove an M&A event, re-run. Show how the system detects the gap and alerts the human with actionable information.

8. **Web visualization (5 min):** Run `caddi-cli viz`, open browser. Show the graph, click nodes, scrub the timeline, show how M&A events change the graph over time. Click an alert, see it highlighted.

9. **RAG integration (2 min):** Run `caddi-cli query "what happened to QuickFab?"` — Claude synthesizes the answer from the M&A registry + order history.

10. **Closing (2 min):** "This is Phase 1. Phase 2 would add PDF document parsing, external M&A data feeds, and multi-format procurement document support."
