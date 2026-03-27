# Hoth Industries Supply Chain Data Analysis

## Table of Contents

- [Overview](#overview)
- [Data Relationships](#data-relationships)
  - [RFQ-to-PO Mapping (Key Discovery)](#rfq-to-po-mapping-key-discovery)
- [1. Supplier Orders](#1-supplier-orders-supplier_orderscsv)
  - [Schema](#schema)
  - [Supplier Name Normalization (Critical Issue)](#supplier-name-normalization-critical-issue)
  - [Cluster-Based Normalization](#cluster-based-normalization)
  - [Delivery Performance](#delivery-performance)
- [2. Quality Inspections](#2-quality-inspections-quality_inspectionscsv)
  - [Rejection Reasons by Severity](#rejection-reasons-by-severity)
- [3. RFQ Responses](#3-rfq-responses-rfq_responsescsv)
- [Pydantic Schema](#pydantic-schema)
- [Key Issues Identified (Priority Order)](#key-issues-identified-priority-order)

## Overview

Hoth Industries manufactures air handling and cooling products for data centers. This analysis covers three datasets spanning Oct 2021 - Oct 2025.

| Dataset | Rows | Description |
|---------|------|-------------|
| supplier_orders.csv | 500 | Purchase order line items |
| quality_inspections.csv | 200 | Incoming quality inspection records |
| rfq_responses.csv | 92 | Supplier quotes for RFQs |

## Data Relationships

```
supplier_orders.order_id (48 unique POs, ~10 line items each)
        |
        ├── quality_inspections.order_id (200 inspections, all 48 POs covered)
        |
        └── rfq_responses.rfq_id (45 RFQs, 1:1 sequential mapping to first 45 POs)
```

All 48 order IDs in inspections have matching orders — no orphan inspections.

### RFQ-to-PO Mapping (Key Discovery)

RFQs map **1:1 to POs by sequential sort order**. Each RFQ represents a competitively-quoted line item within a larger multi-line PO:

| RFQ ID | PO ID | RFQ Date | PO Date Range | Validation |
|--------|-------|----------|---------------|------------|
| RFQ-2021-001 | PO-2021-011 | 2021-10-02 | 2021-10-01 to 2021-10-30 | RFQ date within PO range |
| RFQ-2021-002 | PO-2021-021 | 2021-11-03 | 2021-11-02 to 2021-11-28 | RFQ date within PO range |
| RFQ-2021-003 | PO-2021-032 | 2021-12-05 | 2021-12-01 to 2021-12-30 | RFQ date within PO range |
| ... | ... | ... | ... | All 45 confirmed |

**Evidence supporting the mapping:**
- All 45 RFQ quote dates fall within their mapped PO's order date range
- Supplier names (after normalization) overlap between paired RFQ and PO
- Part descriptions differ in naming (e.g., RFQ "Temperature Controller" vs PO "Touch Screen Controller") but represent the same procurement event
- 3 POs (PO-2025-480, PO-2025-490, PO-2025-501) have no corresponding RFQ — these may have been sole-sourced or used blanket orders

The mapping function is implemented in `rag/models.py:build_rfq_to_po_map()`.

---

## 1. Supplier Orders (`supplier_orders.csv`)

### Schema

| Column | Type | Nulls | Notes |
|--------|------|-------|-------|
| order_id | str | 0 | Format: `PO-YYYY-NNN` (48 unique POs) |
| supplier_name | str | 0 | **9 raw variants mapping to 6 canonical suppliers** |
| part_number | str | 0 | 54 unique part numbers |
| part_description | str | 0 | Human-readable part name |
| order_date | date | 0 | Range: 2021-10-01 to 2025-09-28 |
| promised_date | date | 0 | Expected delivery date |
| actual_delivery_date | date | **8** | Missing for most recent PO (PO-2025-501, not yet delivered) |
| quantity | int | 0 | Range: 15 to 1,195 |
| unit_price | float | 0 | Range: $7.51 to $2,427.53 |
| po_amount | float | 0 | Range: $775 to $730,000 |

### Supplier Name Normalization (Critical Issue)

The same supplier appears under multiple names. **4 variants all refer to "Apex Manufacturing":**

| Raw Name | Order Count | Canonical Name |
|----------|-------------|----------------|
| APEX MFG | 67 | Apex Manufacturing |
| Apex Mfg | 63 | Apex Manufacturing |
| APEX Manufacturing Inc | 57 | Apex Manufacturing |
| Apex Manufacturing Inc | 50 | Apex Manufacturing |
| **Apex total** | **237** | **47.4% of all orders** |
| AeroFlow Systems | 52 | AeroFlow Systems |
| Precision Thermal Co | 49 | Precision Thermal Co |
| QuickFab Industries | 50 | QuickFab Industries |
| Stellar Metalworks | 52 | Stellar Metalworks |
| TitanForge LLC | 60 | TitanForge LLC |

Without normalization, Apex appears as 4 separate small suppliers instead of the dominant supplier handling nearly half of all orders.

### Cluster-Based Normalization

Implemented in `rag/supplier_clustering.py`. Three methods benchmarked:

1. **Jaccard** — tokenize with abbreviation expansion, pairwise Jaccard similarity, union-find clustering
2. **Embedding** — encode names with sentence-transformers (`all-MiniLM-L6-v2`), cluster by cosine similarity
3. **Hybrid** (default) — weighted combination: `0.4 * Jaccard + 0.6 * Embedding`, union-find at threshold >= 0.55

**Tokenization pipeline** (shared by Jaccard and Hybrid):
1. Lowercase, expand abbreviations (`mfg` -> `manufacturing`, `eng` -> `engineering`, etc.)
2. Strip legal suffixes (`Inc`, `LLC`, `Co`, `Corp`, `Ltd`)
3. Return token set

**How confusable names are handled:**

| Name A | Name B | Jaccard | Embedding Cosine | Hybrid Score | Clustered? |
|--------|--------|---------|-----------------|--------------|------------|
| APEX MFG | Apex Manufacturing Inc | 1.00 | ~0.75 | ~0.85 | Yes |
| APEX MFG | APEX Farms | 0.33 | ~0.65 | ~0.52 | **No** |
| Stellar Metalworks | Stellar Dynamics | 0.33 | ~0.55 | ~0.46 | **No** |

#### Benchmark Results (pairwise precision/recall/F1)

Tested across 6 scenarios with increasing difficulty:

| Scenario | Jaccard P/R/F1 | Embedding P/R/F1 | Hybrid P/R/F1 |
|----------|---------------|------------------|---------------|
| **Real data** (9 raw -> 6 canonical) | 100/100/**100%** | 100/33/50% | 100/100/**100%** |
| **Confusables** (Apex Farms, Logistics, Stellar Dynamics) | 100/100/**100%** | 100/60/75% | 100/100/**100%** |
| **Abbreviations** (eng, sys, svcs, tech) | 100/100/**100%** | 100/73/85% | 100/100/**100%** |
| **Typos** (Aeroflw, Systms, Precison) | 100/0/**0%** | 100/25/40% | 100/83/**91%** |
| **Semantic** (Production~Manufacturing, Heat~Thermal) | 100/17/**29%** | 100/100/**100%** | 100/100/**100%** |
| **Mixed** (all challenges combined) | 100/91/**96%** | 100/65/79% | 100/100/**100%** |
| | | | |
| **Average F1** | **70.7%** | **71.4%** | **98.5%** |

#### Key Findings

- **Jaccard** excels at abbreviations (token expansion makes "MFG" = "Manufacturing") but is blind to typos and semantic similarity
- **Embedding** excels at semantic similarity ("Production" ~ "Manufacturing") but struggles with abbreviations ("MFG" is distant from "Manufacturing" in embedding space)
- **Hybrid** combines both strengths: **98.5% average F1** vs 70.7% (Jaccard) and 71.4% (Embedding)

#### Threshold Sensitivity (Hybrid)

| Combined Threshold | Precision | Recall | F1 |
|-------------------|-----------|--------|-----|
| 0.40-0.50 | 50-58% | 100% | 67-73% |
| **0.55-0.60** | **100%** | **100%** | **100%** |
| 0.65 | 100% | 91% | 96% |
| 0.70 | 100% | 74% | 85% |

Default combined threshold of **0.55** is optimal — below 0.50, unrelated names merge; above 0.60, recall starts dropping.

### Delivery Performance

- **88 of 500 orders (17.6%) were delivered late**
- 8 orders have no delivery date (PO-2025-501, still pending)

| Supplier (canonical) | Late Orders | Avg Days Late | Max Days Late |
|---------------------|-------------|---------------|---------------|
| **QuickFab Industries** | **29** | **22.1** | **34** |
| Apex Manufacturing | 35 | 4.1 | 7 |
| AeroFlow Systems | 10 | 3.6 | 7 |
| Precision Thermal Co | 5 | 3.4 | 7 |
| Stellar Metalworks | 5 | 4.4 | 7 |
| TitanForge LLC | 4 | 4.8 | 7 |

**QuickFab Industries is a major delivery risk** — 58% of their orders are late, averaging 22 days, with some arriving over a month past due. All other suppliers cap out at 7 days late max.

---

## 2. Quality Inspections (`quality_inspections.csv`)

### Schema

| Column | Type | Nulls | Notes |
|--------|------|-------|-------|
| inspection_id | str | 0 | Format: `INS-NNN` (200 unique) |
| order_id | str | 0 | FK to supplier_orders (all 48 POs covered) |
| inspection_date | date | 0 | Range: 2021-11-18 to 2025-10-05 |
| parts_inspected | int | 0 | Range: 15 to 1,195 |
| parts_rejected | int | 0 | Range: 0 to 190 |
| rejection_reason | str | 0 | 21 distinct reasons (including "Passed") |
| rework_required | bool | 0 | Yes/No |

### Rejection Reasons by Severity

Categorized into 5 severity tiers:

#### STRUCTURAL (critical — material/process defects)
| Reason | Occurrences | Parts Rejected | Rejection Rate |
|--------|-------------|----------------|----------------|
| Welding defects multiple tubes | 3 | 176 | **20.4%** |
| Poor weld quality | 3 | 191 | **18.7%** |
| Wrong alloy used | 3 | 46 | **18.0%** |
| Tube spacing incorrect | 4 | 310 | **16.6%** |
| Leaked during pressure test | 3 | 62 | **13.7%** |
| Material grade wrong | 2 | 44 | **13.5%** |
| Coil spacing wrong | 1 | 8 | 13.1% |
| Tube alignment poor | 1 | 25 | 13.0% |
| Wrong thickness - too thin | 2 | 228 | **11.6%** |

#### SHIPPING (transit damage)
| Reason | Occurrences | Parts Rejected | Rejection Rate |
|--------|-------------|----------------|----------------|
| Blade damage in shipping | 11 | 136 | 3.2% |

#### CALIBRATION (precision/functional)
| Reason | Occurrences | Parts Rejected | Rejection Rate |
|--------|-------------|----------------|----------------|
| Calibration slightly off | 11 | 51 | 2.7% |
| Sensor drift | 10 | 82 | 2.5% |
| Balance issues | 15 | 110 | 2.4% |

#### MACHINING (surface/finish defects)
| Reason | Occurrences | Parts Rejected | Rejection Rate |
|--------|-------------|----------------|----------------|
| Burrs on edges | 17 | 116 | 2.9% |
| Minor machining marks | 19 | 166 | 3.0% |
| Minor surface finish issues | 11 | 44 | 2.1% |

#### COSMETIC (minor appearance)
| Reason | Occurrences | Parts Rejected | Rejection Rate |
|--------|-------------|----------------|----------------|
| Cosmetic only | 13 | 125 | 3.1% |
| Minor cosmetic | 17 | 123 | 3.0% |
| Surface scratches | 7 | 59 | 3.2% |
| Paint chips | 15 | 125 | 2.4% |

### Key Findings
- **Structural defects have 10-20% rejection rates** vs 2-3% for cosmetic/machining
- Welding and tube-related issues are the most critical quality problems
- "Passed" appears in 32 inspections (16%) — most orders have some rejections
- Multiple inspections per PO suggest batch-by-batch receiving inspection

---

## 3. RFQ Responses (`rfq_responses.csv`)

### Schema

| Column | Type | Nulls | Notes |
|--------|------|-------|-------|
| rfq_id | str | 0 | Format: `RFQ-YYYY-NNN` (45 unique RFQs) |
| supplier_name | str | 0 | 8 raw variants (same normalization issue) |
| part_description | str | 0 | 20 unique parts quoted |
| quote_date | date | 0 | Range: 2021-10-02 to 2025-08-31 |
| quoted_price | float | 0 | Range: $7.33 to $2,427.53 |
| lead_time_weeks | int | 0 | Range: 2 to 6 weeks |
| notes | str | 0 | Free-text (stock status, quality tier, etc.) |

### RFQ Competition
- 45 RFQs with 2-3 quotes each (average 2.0 responses per RFQ)
- Most-quoted parts: Vibration Mount (6 RFQs), Aluminum Fins (6), HEPA Filter Industrial (4)
- Some RFQs have only 1 response = **sole-source risk**

### Frequently Quoted Parts

| Part | RFQ Count | Avg Price | Price Spread |
|------|-----------|-----------|--------------|
| Aluminum Fins | 6 | $8.44 | $7.33 - $10.83 |
| Vibration Mount | 6 | $29.05 | $25.22 - $32.69 |
| HEPA Filter Industrial | 4 | $67.55 | $64.25 - $71.37 |
| 28 inch Fan High CFM | 3 | $387.16 | $361.22 - $416.40 |
| Steel Bracket | 3 | $14.77 | $10.56 - $19.54 |
| Temperature Controller | 3 | $462.30 | $442.04 - $476.26 |

---

## Pydantic Schema

Validated models are defined in `rag/models.py`:

```python
class SupplierOrder(BaseModel):
    order_id: str                          # PO-2021-011
    supplier_name_raw: str                 # Original messy name
    supplier_name: str                     # Computed: normalized canonical name
    part_number: str
    part_description: str
    order_date: date
    promised_date: date
    actual_delivery_date: Optional[date]   # None for 8 pending orders
    quantity: int
    unit_price: float
    po_amount: float
    days_late: Optional[int]               # Computed: 0 if on-time, None if pending
    is_late: Optional[bool]                # Computed

class QualityInspection(BaseModel):
    inspection_id: str
    order_id: str                          # FK to SupplierOrder
    inspection_date: date
    parts_inspected: int
    parts_rejected: int
    rejection_reason: str
    rework_required: bool
    rejection_rate: float                  # Computed: rejected/inspected
    severity: RejectionSeverity            # Computed: enum classification

class RFQResponse(BaseModel):
    rfq_id: str
    supplier_name_raw: str
    supplier_name: str                     # Computed: normalized
    part_description: str
    quote_date: date
    quoted_price: float
    lead_time_weeks: int
    notes: Optional[str]
```

### Severity Enum
```
PASSED     → "Passed"
COSMETIC   → surface scratches, paint chips, minor cosmetic, cosmetic only
MACHINING  → burrs, machining marks, surface finish issues
CALIBRATION → calibration, sensor drift, balance issues
STRUCTURAL → welding, tube spacing/alignment, wrong alloy/thickness, leaks
SHIPPING   → blade damage in shipping
```

---

## Key Issues Identified (Priority Order)

1. **Supplier name chaos** — 4 Apex variants make accurate spend analysis impossible without normalization
2. **QuickFab delivery problem** — 58% late rate, avg 22 days late (vs 3-5 for everyone else)
3. **Structural quality defects** — 10-20% rejection rates on welding/tube issues indicate process control failures at certain suppliers
4. **Missing delivery dates** — 8 orders (PO-2025-501) have no actual_delivery_date
5. **RFQ-to-PO linking** — sequential 1:1 mapping confirmed (see Data Relationships); part descriptions differ between systems but temporal + supplier alignment validates the join
6. **Sole-source parts** — some RFQs have only 1 response, creating supply risk
7. **3 POs without RFQs** — PO-2025-480, PO-2025-490, PO-2025-501 have no corresponding RFQ (sole-sourced or blanket orders?)
