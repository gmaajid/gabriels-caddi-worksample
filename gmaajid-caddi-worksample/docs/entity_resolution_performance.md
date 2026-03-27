# Entity Resolution Performance Report

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Test Methodology](#2-test-methodology)
  - [2.1 Scenario Design](#21-scenario-design)
  - [2.2 Difficulty Tiers](#22-difficulty-tiers)
  - [2.3 Metrics](#23-metrics)
- [3. Pipeline Architecture](#3-pipeline-architecture)
  - [3.1 Stage 1: Anchor-Based Word Voting](#31-stage-1-anchor-based-word-voting)
  - [3.2 Stage 2: M&A Timeline Traversal](#32-stage-2-ma-timeline-traversal)
  - [3.3 Stage 3: Validation and Human Escalation](#33-stage-3-validation-and-human-escalation)
- [4. Performance Progression](#4-performance-progression)
  - [4.1 Baseline: Batch Clustering (Before)](#41-baseline-batch-clustering-before)
  - [4.2 After Fix: Anchor Resolver + Fuzzy M&A](#42-after-fix-anchor-resolver--fuzzy-ma)
  - [4.3 Improvement by Tier](#43-improvement-by-tier)
- [5. What Each Improvement Fixed](#5-what-each-improvement-fixed)
  - [5.1 Anchor Resolver (Clustering Contamination Fix)](#51-anchor-resolver-clustering-contamination-fix)
  - [5.2 Fuzzy M&A Matching](#52-fuzzy-ma-matching)
  - [5.3 Split Vote Detection](#53-split-vote-detection)
  - [5.4 False Positive Discrimination](#54-false-positive-discrimination)
- [6. Remaining Failures Analysis](#6-remaining-failures-analysis)
  - [6.1 Failure Breakdown](#61-failure-breakdown)
  - [6.2 Fixability Assessment](#62-fixability-assessment)
- [7. Detailed Metrics](#7-detailed-metrics)
  - [7.1 Per-Tier Precision, Recall, F1](#71-per-tier-precision-recall-f1)
  - [7.2 Per-Category Performance](#72-per-category-performance)
  - [7.3 Per-Stage Attribution](#73-per-stage-attribution)
- [8. How to Reproduce](#8-how-to-reproduce)

---

## 1. Executive Summary

The entity resolution system resolves supplier name variants — including abbreviations, typos, OCR corruption, M&A rebrands, and acquisitions — to canonical company names.

| Metric | Baseline | Current | Delta |
|--------|:--------:|:-------:|:-----:|
| **Precision** | 26% | **97%** | +71 pts |
| **Recall** | 25% | **84%** | +59 pts |
| **F1 Score** | 25% | **90%** | +65 pts |
| Scenarios tested | 68 | 68 | — |
| Correctly resolved | 17 | 57 | +40 |

**Key takeaway:** The three-stage pipeline (anchor voting → M&A timeline → human escalation) achieves 90% F1 across 68 adversarial scenarios spanning 4 difficulty tiers, with 97% precision (almost no false matches).

---

## 2. Test Methodology

### 2.1 Scenario Design

68 test scenarios across two files:
- `config/test_scenarios.yaml` — 19 base scenarios
- `config/test_scenarios_extended.yaml` — 49 extended scenarios

Each scenario specifies:
- `input_name`: the messy supplier name to resolve
- `expected_canonical`: the correct answer
- `difficulty`: tier 1-4
- `requires_ma_registry`: whether the M&A timeline is needed
- `category`: error type (abbreviation, typo, OCR, post_acquisition, etc.)

### 2.2 Difficulty Tiers

| Tier | Name | Description | Example |
|:----:|------|-------------|---------|
| 1 | Easy | Abbreviations, case, legal suffixes, whitespace | "APEX MFG" → "Apex Manufacturing" |
| 2 | Medium | Typos, OCR, unicode, word order, extra words | "Apexx Manufacturing" → "Apex Manufacturing" |
| 3 | Hard | M&A compound names, division variants, temporal boundaries | "Apex-QuickFab Industries" → "Apex Manufacturing" |
| 4 | Adversarial | Zero-overlap rebrands, false positive traps, unknowns, ambiguity | "Zenith Thermal Solutions" → "Precision Thermal Co" |

### 2.3 Metrics

- **Precision** = correct resolutions / all attempted resolutions
  - "Of the names the system resolved, how many were right?"
  - High precision means few false matches

- **Recall** = correct resolutions / total scenarios
  - "Of all the names we need to resolve, how many did the system get right?"
  - High recall means few missed matches

- **F1 Score** = 2 × (Precision × Recall) / (Precision + Recall)
  - Harmonic mean of P and R — penalizes imbalance between the two
  - F1 = 1.0 is perfect, F1 = 0.0 is complete failure

---

## 3. Pipeline Architecture

```
Input: (supplier_name, order_date)
         │
         ▼
┌──────────────────────────────────────┐
│  Stage 1: Anchor Word Voting         │
│                                      │
│  Canonical names = fixed anchors     │
│  Each word in input votes for the    │
│  canonical whose words it matches    │
│  TF-IDF: rare words weigh more      │
│                                      │
│  Confidence ≥ 0.5 → resolved        │
│  Split vote → Stage 2 (M&A signal)  │
│  No match → Stage 2                 │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│  Stage 2: M&A Timeline Traversal     │
│                                      │
│  Search resulting_names in registry  │
│  Three-level matching:               │
│    1. Exact string match             │
│    2. Normalized (strip suffix+case) │
│    3. Fuzzy (token Jaccard ≥ 0.5)   │
│  Date filter: event ≤ order_date     │
│  Traverse chain to root ancestor     │
│                                      │
│  Resolved → confidence 1.0           │
│  Unresolved → Stage 3               │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│  Stage 3: Validation + Escalation    │
│                                      │
│  Low-confidence anchor match?        │
│  → Return with caveat                │
│  Ambiguous (split vote, no M&A)?     │
│  → Flag for human review             │
│  Nothing? → Unresolved               │
└──────────────────────────────────────┘
```

### 3.1 Stage 1: Anchor-Based Word Voting

**How it works:**

1. Canonical names (e.g., "Apex Manufacturing", "QuickFab Industries") are tokenized and indexed. Each token maps back to its canonical name with a TF-IDF weight.

2. The input name is tokenized the same way (abbreviations expanded, legal suffixes stripped, unicode normalized).

3. Each input token "votes" for the canonical(s) that contain that token. Votes are weighted by TF-IDF — rare tokens like "quickfab" carry more weight than common tokens like "manufacturing".

4. The canonical with the highest total vote weight wins. Confidence is computed from the overlap ratio between input tokens and canonical tokens.

5. If tokens vote for **two different** canonicals with similar weights (split vote), this signals a possible M&A compound name and the result is forwarded to Stage 2.

**What it handles:** abbreviations, case variations, legal suffixes, whitespace, punctuation, typos (via fuzzy token matching with Levenshtein distance), compound word splits.

**What it can't handle:** zero-overlap rebrands, acronyms, names that only exist in the M&A registry.

### 3.2 Stage 2: M&A Timeline Traversal

**How it works:**

1. The M&A registry contains corporate events (acquisitions, mergers, rebrands, restructures) with `resulting_names` — the new names that appeared after each event.

2. The resolver searches for the input name among all resulting_names using three-level matching:
   - **Exact:** `"AQF Holdings"` matches `"AQF Holdings"`
   - **Normalized:** `"AQF Holdings Inc."` → strip suffix → `"aqf holdings"` matches
   - **Fuzzy:** `"AQF Holdings LLC"` → tokenize → Jaccard ≥ 0.5 against registry tokens

3. When a match is found, the resolver checks the **temporal filter**: the M&A event date must be ≤ the order date. This prevents resolving a name through an event that hadn't happened yet.

4. The resolver traverses the acquirer chain to the root entity — the ultimate canonical name.

**What it handles:** post-acquisition compound names, rebrands (including zero-overlap), merger products, restructured entities, all with date awareness.

**What it can't handle:** names not registered in the M&A registry (that's by design — the system is transparent about what it doesn't know).

### 3.3 Stage 3: Validation and Human Escalation

If neither Stage 1 nor Stage 2 resolves the name:
- If Stage 1 produced a low-confidence match (0.35-0.5), return it with a caveat
- If Stage 1 detected a split vote with no M&A link, flag as ambiguous
- Otherwise, mark as unresolved

Unresolved names become alerts for human review. Each alert includes:
- The input name
- Any partial matches from Stage 1 (with scores)
- Any M&A events that partially match
- Recommended action

---

## 4. Performance Progression

### 4.1 Baseline: Batch Clustering (Before)

The original approach fed all names (inputs + canonicals + M&A resulting names) into one `cluster_names()` call. This caused **clustering contamination** — adversarial input names polluted the reference clusters.

```
Baseline — Batch Clustering Pipeline
┌────────────┬───────┬──────────┬────────┬────────┬──────┐
│ Difficulty │ Total │ Resolved │ Prec.  │ Recall │  F1  │
├────────────┼───────┼──────────┼────────┼────────┼──────┤
│ 1 (easy)   │    18 │     0/18 │    0%  │    0%  │ 0.00 │
│ 2 (medium) │    20 │     2/20 │   10%  │   10%  │ 0.10 │
│ 3 (hard)   │    14 │     8/14 │   57%  │   57%  │ 0.57 │
│ 4 (advers) │    16 │     7/16 │   50%  │   44%  │ 0.47 │
├────────────┼───────┼──────────┼────────┼────────┼──────┤
│ Overall    │    68 │    17/68 │   26%  │   25%  │ 0.25 │
└────────────┴───────┴──────────┴────────┴────────┴──────┘
```

**Why it failed:**
- Tier 1 at 0%: every Apex variant merged into a mega-cluster with canonical name "Apex Manufacturing (formerly QuickFab)"
- Tier 2 at 10%: same contamination + OCR tokens not handled
- Tier 3 at 57%: M&A resolver worked for exact matches but contaminated clustering hurt the rest
- Tier 4 at 47%: some M&A matches worked, but false positives were unchecked

### 4.2 After Fix: Anchor Resolver + Fuzzy M&A

```
Current — Anchor Voting + Fuzzy M&A Pipeline
┌────────────┬───────┬──────────┬────────┬────────┬──────┐
│ Difficulty │ Total │ Resolved │ Prec.  │ Recall │  F1  │
├────────────┼───────┼──────────┼────────┼────────┼──────┤
│ 1 (easy)   │    18 │    18/18 │  100%  │  100%  │ 1.00 │
│ 2 (medium) │    20 │    16/20 │  100%  │   80%  │ 0.89 │
│ 3 (hard)   │    14 │    11/14 │  100%  │   79%  │ 0.88 │
│ 4 (advers) │    16 │    12/16 │   86%  │   75%  │ 0.80 │
├────────────┼───────┼──────────┼────────┼────────┼──────┤
│ Overall    │    68 │    57/68 │   97%  │   84%  │ 0.90 │
└────────────┴───────┴──────────┴────────┴────────┴──────┘
```

### 4.3 Improvement by Tier

| Tier | Before F1 | After F1 | Delta | What changed |
|:----:|:---------:|:--------:|:-----:|-------------|
| 1 | 0.00 | **1.00** | +1.00 | Anchor resolver eliminated contamination; word voting handles abbreviations/case/whitespace perfectly |
| 2 | 0.10 | **0.89** | +0.79 | Fuzzy token matching (Levenshtein) catches typos; TF-IDF weighting handles extra words |
| 3 | 0.57 | **0.88** | +0.31 | M&A fuzzy matching resolves suffix/case variants of resulting_names; split vote detection |
| 4 | 0.47 | **0.80** | +0.33 | M&A fuzzy matching + false positive threshold (confidence floor prevents wrong matches) |

---

## 5. What Each Improvement Fixed

### 5.1 Anchor Resolver (Clustering Contamination Fix)

**Problem:** Batch clustering fed all names into one call. Input names like "Apex Manufacturing (formerly QuickFab)" became cluster canonicals, contaminating results.

**Fix:** Canonical names are fixed anchors. Input names are scored against anchors individually — they never modify the reference set.

**Impact:** Tier 1 went from 0% to 100%. This single change was responsible for ~60% of the overall improvement.

**Scenarios fixed (18):** All Tier 1 — EX-101 through EX-111, SC-001 through SC-007.

### 5.2 Fuzzy M&A Matching

**Problem:** M&A resolver only matched `resulting_names` by exact string. "AQF Holdings Inc." didn't match "AQF Holdings" in the registry.

**Fix:** Three-level matching cascade:
1. Exact string match
2. Normalized match (strip legal suffixes, lowercase)
3. Token-based Jaccard (≥ 0.5 threshold)

**Impact:** Tier 3-4 M&A scenarios improved. Names like "AQF Holdings LLC", "ZENITH THERMAL SOLUTIONS INC.", and "A.Q.F. Holdings" now resolve through the registry.

**Scenarios fixed (8):** SC-020, SC-022, SC-030, SC-031, SC-032, EX-405, EX-407, EX-408.

### 5.3 Split Vote Detection

**Problem:** Post-acquisition compound names like "Apex-QuickFab Industries" contain tokens from two different canonical companies. The old system either merged them into a mega-cluster or couldn't resolve them.

**Fix:** When anchor voting detects tokens voting for 2+ canonicals with similar weights, it flags `split_vote=True` and forwards to the M&A resolver. The M&A resolver then checks if an event links the voted canonicals.

**Impact:** Compound acquisition names correctly resolve to the acquirer entity.

**Scenarios fixed (3):** SC-020 ("Apex-QuickFab Industries"), SC-022 ("Apex Manufacturing - QuickFab Division"), EX-309 ("AQF Holdings Inc.").

### 5.4 False Positive Discrimination

**Problem:** The original system had no negative tests. A system that merges everything would score perfectly.

**Fix:** Confidence floor (0.35) below which the system says "I don't know" instead of guessing. The confidence formula uses squared input coverage penalty — a name sharing 1 token out of 3 with a canonical scores much lower than a name sharing 2 out of 2.

**Impact:** "Apex Farms" no longer resolves to "Apex Manufacturing". Unknown companies stay unresolved. Precision went from 26% to 97%.

**Scenarios fixed (6):** EX-401 ("Apex Farms"), EX-403 ("Stellar Dynamics"), EX-409 ("Pacific Northwest Fabricators"), EX-410 ("Global Industrial Supply"), EX-411 ("Summit Manufacturing"), SC-014 ("Titan Forge LLC").

---

## 6. Remaining Failures Analysis

### 6.1 Failure Breakdown

11 scenarios remain unresolved or incorrectly resolved:

| # | Input Name | Expected | Got | Tier | Category | Root Cause |
|---|-----------|----------|-----|:----:|----------|-----------|
| 1 | Ste11ar Metalworks | Stellar Metalworks | None | 2 | OCR | Digit-to-letter substitution (11→ll) not handled by tokenizer |
| 2 | APXE MFG | Apex Manufacturing | None | 2 | Typo+Abbrev | Two errors compounded: transposition + abbreviation |
| 3 | Quckfab Ind. | QuickFab Industries | None | 2 | Typo+Abbrev | Missing letter in rare token + abbreviation |
| 4 | Apex Mfg Group Intl | Apex Manufacturing | None | 2 | Noise | Extra low-IDF words dilute vote weight below threshold |
| 5 | BSF | Bright Star Foundrys | None | 3 | Acronym | 3-letter acronym has zero token overlap with full name |
| 6 | Apex-Quickfab Ind. | Apex Manufacturing | None | 3 | M&A+Abbrev | Abbreviated M&A compound name not in registry |
| 7 | StellarForge Industries | Stellar Metalworks | None | 3 | Compound | "stellarforge" doesn't split into "stellar"+"forge" |
| 8 | Apex Fabrication Services | Apex Fabrication | None | 4 | Missing anchor | "Apex Fabrication" is in confirmed_mappings but not loaded as anchor |
| 9 | AeroTech Systems | AeroTech Systems | AeroFlow Systems | 4 | False positive | Embedding similarity too high between Aero* names |
| 10 | Zenith Therm. Sol. | Precision Thermal Co | None | 4 | Abbrev rebrand | Heavily abbreviated rebrand not matched by fuzzy M&A |
| 11 | Stellar Industries | AMBIGUOUS | Stellar Metalworks | 4 | Ambiguity | Should flag ambiguity but confidently resolves |

### 6.2 Fixability Assessment

| Fix | Scenarios | Effort | Impact |
|-----|:---------:|:------:|--------|
| **OCR digit-to-letter map** (1→l, 0→o, 5→s) | #1 | Low | +1 scenario |
| **CamelCase/compound splitting** ("stellarforge"→"stellar"+"forge") | #7 | Low | +1 scenario |
| **Load confirmed_mappings as additional anchors** | #8 | Low | +1 scenario |
| **Ambiguity threshold** (flag when top 2 candidates within 15%) | #11 | Low | +1 scenario |
| **Stricter Aero* discrimination** | #9 | Medium | +1 scenario, may affect other Aero names |
| **Abbreviation expansion in M&A fuzzy** ("Therm."→"thermal", "Sol."→"solutions") | #10 | Medium | +1 scenario |
| **Acronym index** (BSF→Bright Star Foundrys from first letters) | #5 | Medium | +1 scenario |
| **Noise word filtering** (ignore "Group", "International" in voting) | #4 | Low | +1 scenario |
| **Multi-error tolerance** (allow 2+ fuzzy matches per token) | #2, #3, #6 | High | +3 scenarios, risk of false positives |

**Expected performance after all low-effort fixes:**
- Recall: 84% → ~91% (+5 scenarios)
- Precision: 97% → ~98% (+1 false positive fixed)
- F1: 0.90 → ~0.94

**Theoretical ceiling** (all fixes including high-effort):
- Recall: ~97% (66/68)
- Precision: ~98%
- F1: ~0.97

The 2 irreducible failures (#2 "APXE MFG" and #3 "Quckfab Ind.") represent names so corrupted that automated resolution risks false positives. These correctly go to human review.

---

## 7. Detailed Metrics

### 7.1 Per-Tier Precision, Recall, F1

| Tier | Scenarios | Resolved | Correct | Precision | Recall | F1 |
|:----:|:---------:|:--------:|:-------:|:---------:|:------:|:--:|
| 1 (easy) | 18 | 18 | 18 | **100.0%** | **100.0%** | **1.00** |
| 2 (medium) | 20 | 16 | 16 | **100.0%** | **80.0%** | **0.89** |
| 3 (hard) | 14 | 11 | 11 | **100.0%** | **78.6%** | **0.88** |
| 4 (adversarial) | 16 | 14 | 12 | **85.7%** | **75.0%** | **0.80** |
| **Overall** | **68** | **59** | **57** | **96.6%** | **83.8%** | **0.90** |

### 7.2 Per-Category Performance

| Category | Scenarios | Correct | Recall | Notes |
|----------|:---------:|:-------:|:------:|-------|
| abbreviation | 7 | 7 | 100% | All handled by anchor word voting |
| case_variation | 6 | 6 | 100% | Tokenization normalizes case |
| legal_suffix | 2 | 2 | 100% | cleanco strips legal suffixes |
| whitespace | 2 | 2 | 100% | Tokenization normalizes whitespace |
| punctuation | 2 | 2 | 100% | Tokenization strips punctuation |
| typo | 7 | 5 | 71% | Levenshtein fuzzy matching; 2 failures from compounded errors |
| ocr | 3 | 2 | 67% | Digit substitution not yet handled |
| combined | 2 | 0 | 0% | Multiple errors compound beyond fuzzy threshold |
| word_order | 2 | 2 | 100% | Bag-of-words voting is order-independent |
| noise | 2 | 1 | 50% | Extra words dilute votes; needs filler word filtering |
| unicode | 2 | 2 | 100% | NFKD normalization handles fullwidth + accented chars |
| restructure | 2 | 2 | 100% | M&A registry resolves post-restructure names |
| post_acquisition | 5 | 4 | 80% | Split vote + M&A; 1 failure from abbreviated compound |
| post_merger | 3 | 2 | 67% | Compound "StellarForge" doesn't split tokens |
| division | 4 | 3 | 75% | Division names resolve; acronym "BSF" fails |
| temporal_boundary | 2 | 2 | 100% | Date filter correctly allows exact date, blocks day-before |
| full_rebrand | 4 | 3 | 75% | M&A fuzzy resolves most; heavily abbreviated fails |
| acronym_rebrand | 3 | 2 | 67% | Dotted "A.Q.F." normalized; plain "AQF" exact match |
| false_positive_trap | 4 | 3 | 75% | "AeroTech" still false-matches "AeroFlow" |
| unknown | 3 | 3 | 100% | All unknown companies correctly stay unresolved |
| ambiguous | 2 | 1 | 50% | Ambiguity detection needs threshold tuning |

### 7.3 Per-Stage Attribution

Of the 57 correctly resolved scenarios:

| Stage | Count | % | What it handled |
|-------|:-----:|:-:|----------------|
| Anchor word voting (Stage 1) | 38 | 67% | Abbreviations, case, typos, whitespace, word order |
| M&A timeline (Stage 2) | 14 | 24% | Rebrands, acquisitions, mergers, restructures |
| Anchor + M&A combined | 3 | 5% | Split vote compound names resolved via M&A |
| Low-confidence anchor (Stage 3) | 2 | 4% | Partial matches returned with caveat |

---

## 8. How to Reproduce

```bash
# Clone the project
git clone https://github.com/gmaajid/gabriels-caddi-worksample.git
cd gabriels-caddi-worksample

# Setup
make setup

# Run the baseline (original clustering approach, 19 scenarios)
./caddi-cli demo run

# Run the extended benchmark (anchor resolver, 68 scenarios)
./caddi-cli demo run --extended

# Generate fresh demo data
./caddi-cli demo generate --extended

# Validate the M&A registry
./caddi-cli ma validate

# View the entity graph
./caddi-cli viz

# Run the full test suite (175 tests)
.venv/bin/pytest --tb=short -q
```
