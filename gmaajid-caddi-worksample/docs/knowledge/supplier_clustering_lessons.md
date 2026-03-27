# Supplier Name Clustering: Problems and Solutions

## Table of Contents

- [Problem 1: OCR and Unicode Corruption](#problem-1-ocr-and-unicode-corruption)
- [Problem 2: Shared Filler Words (High Token Overlap)](#problem-2-shared-filler-words-high-token-overlap)
- [Problem 3: Embedding False Merges (AeroFlow vs AeroTech)](#problem-3-embedding-false-merges-aeroflow-vs-aerotech)
- [Problem 4: Abbreviation Explosion](#problem-4-abbreviation-explosion)
- [Problem 5: Minimal Distinguishing Information](#problem-5-minimal-distinguishing-information)
- [Summary: What Worked, What Didn't](#summary-what-worked-what-didnt)

## Problem 1: OCR and Unicode Corruption

**Symptoms:** "Ste1lar Metalworks" doesn't match "Stellar Metalworks". "AéroFlow" doesn't match "AeroFlow". Non-breaking spaces (\u00a0) break tokenization.

**Root Cause:** Tokenization operates on exact character matches. A single substituted digit ("1" for "l"), accented character, or invisible unicode space creates a completely different token.

**Solution: Character Normalization Pipeline** (`_normalize_chars` in supplier_clustering.py)
1. Unicode NFKD decomposition strips accents: "é" → "e"
2. Whitespace normalization replaces non-breaking spaces, zero-width spaces, etc. with regular spaces
3. Embedded digit stripping removes digits from mostly-alpha tokens: "Ste1lar" → "Stellar"
4. CamelCase boundary splitting: "StellarMetalworks" → "Stellar Metalworks"

**Result:** OCR scenarios improved from 0% → 14% F1 for Jaccard (tokens now match). Embedding still handles remaining cases. Unicode normalization fixed the \u00a0 and accent issues directly.

**Limitation:** All-caps compound words like "TITANFORGE" lack CamelCase boundaries and remain unsplit. The embedding component handles these via semantic similarity.

## Problem 2: Shared Filler Words (High Token Overlap)

**Symptoms:** "Pacific Steel Manufacturing" merges with "Pacific Thermal Manufacturing" because Jaccard similarity = {pacific, manufacturing} / {pacific, steel, thermal, manufacturing} = 2/4 = 0.5, meeting the threshold.

**Root Cause:** Plain Jaccard treats all tokens equally. Common tokens like "manufacturing", "national", "engineering" contribute as much as distinguishing tokens like "steel" vs "thermal".

**Solution: TF-IDF Weighted Jaccard** (`tfidf_jaccard_similarity` in supplier_clustering.py)
- Compute IDF (inverse document frequency) across all names in the corpus
- Tokens appearing in many names (manufacturing, national) get low weight
- Distinguishing tokens (steel, thermal, pacific, atlantic) get high weight
- Sum(IDF of shared tokens) / Sum(IDF of all tokens) replaces plain intersection/union

**Result:** Shared Filler scenario improved from 18% → 40% precision with hybrid_v2 (the only method that uses TF-IDF). The scenario improved from 1 cluster to 2 clusters (partial separation).

**Limitation:** When the corpus is small (only a few names), IDF weights have high variance. The distinguishing token may not have enough IDF differential. TF-IDF Jaccard works better with larger supplier lists.

## Problem 3: Embedding False Merges (AeroFlow vs AeroTech)

**Symptoms:** "AeroFlow Systems" and "AeroTech Systems" cluster together because they share the "Aero___Systems" embedding pattern. Cosine similarity is ~0.85.

**Root Cause:** Sentence-transformers encode semantic meaning — "AeroFlow" and "AeroTech" are both technology-sounding compound words starting with "Aero" and ending with a tech suffix. The model sees them as near-synonyms.

**Solution: Gated Hybrid** (`cluster_hybrid_v2` in supplier_clustering.py)
- Instead of a weighted average (which lets a high embedding score override a low Jaccard score), require BOTH signals to pass minimum thresholds
- Gate condition: Jaccard >= 0.3 AND embedding >= 0.5
- Only if both pass, compute average and check against combined threshold
- This prevents embedding-only merges when Jaccard clearly disagrees

**Result:** Gated hybrid achieves 83.6% average precision on adversarial data (vs 56% for weighted hybrid). But at the cost of recall (34% vs 78%) — it's overly conservative.

**Trade-off:** Hybrid v1 (weighted) remains the default because it scores 92.4% F1 on standard scenarios. Hybrid v2 (gated) is available for high-precision use cases where false merges are more costly than missed matches. The optimal choice depends on the use case:
- **Spend analysis**: Use hybrid v1 (better recall — don't want to undercount a supplier)
- **Compliance/audit**: Use hybrid v2 (better precision — don't want to wrongly merge entities)

## Problem 4: Abbreviation Explosion

**Symptoms:** "National Engineering Services" vs "National Engineering Solutions" — after expanding NATL→National, ENG→Engineering, SVC→Services, the only distinguishing token is "services" vs "solutions" in a 3-token set. Jaccard = 2/4 = 0.5.

**Root Cause:** Same as Problem 2 — when abbreviation expansion creates shared tokens, the distinguishing token gets outvoted. This is exacerbated when the distinguishing words are semantically similar (services/solutions).

**Solution:** TF-IDF weighting partially addresses this (see Problem 2). The expanded abbreviation "engineering" gets lower IDF than "services"/"solutions" if engineering appears in many names. Hybrid_v2 achieves 81.8% F1 vs 63.4% for other methods.

**Limitation:** When "services" and "solutions" are the ONLY entries containing those tokens, their IDF scores are identical, and TF-IDF doesn't help. This is a fundamental limitation of token-based methods for near-synonym distinguishing tokens.

## Problem 5: Minimal Distinguishing Information

**Symptoms:** "ABC Manufacturing - Division A" vs "ABC Manufacturing - Division B" — the only distinguishing information is a single character.

**Root Cause:** When the distinguishing token is "a" vs "b" in a 4-token set, Jaccard = 3/5 = 0.6 > threshold. Even embeddings see "Division A" and "Division B" as very similar.

**Solution:** This is fundamentally pathological — no automated token-level or embedding-level method can reliably distinguish these. Recommended approaches:
1. Human-in-the-loop review for high-similarity pairs
2. Exact-match subdivision rules (if division codes are known)
3. Accept that some cases require manual curation

**Result:** All methods score 30-57% F1. This is documented as a known limit.

## Summary: What Worked, What Didn't

| Fix | Universally Beneficial? | Default Method |
|-----|:----------------------:|:--------------:|
| Character normalization (OCR, unicode, CamelCase) | **Yes** | All methods |
| TF-IDF weighted Jaccard | Partially (small corpus limits IDF) | Hybrid v2 only |
| Gated hybrid (AND logic) | No — trades recall for precision | Hybrid v2 only |

**Default recommendation:** Hybrid v1 (weighted average) with character normalization.
It achieves 92.4% F1 on standard data and 51.8% on adversarial — the best balanced performer.
Use Hybrid v2 when precision matters more than recall (e.g., compliance auditing).
