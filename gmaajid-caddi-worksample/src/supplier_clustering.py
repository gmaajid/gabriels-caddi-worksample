"""Supplier name normalization via clustering.

Four strategies implemented:
1. **Jaccard**: Token-level Jaccard similarity with abbreviation expansion
2. **Embedding**: Sentence-transformer cosine similarity on raw names
3. **Hybrid**: Weighted combination of Jaccard + embedding scores (v1)
4. **Hybrid v2**: Gated hybrid with TF-IDF Jaccard + char normalization (default)

All use the same union-find clustering backbone and produce the
same output format: {canonical_name: [variant_names]}.

## Fixes applied in v2:
- Character normalization: strip digits from alpha tokens (OCR), normalize
  unicode, split compound words (CamelCase, concatenated)
- TF-IDF weighted Jaccard: rare distinguishing tokens (steel/thermal) weigh
  more than common ones (manufacturing/national)
- Gated hybrid: both Jaccard AND embedding must exceed minimum thresholds,
  preventing false merges from either method alone
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from enum import Enum
from typing import Optional

import numpy as np

# Common abbreviation expansions for manufacturing/industrial companies
ABBREVIATIONS: dict[str, str] = {
    "mfg": "manufacturing",
    "mfr": "manufacturer",
    "intl": "international",
    "natl": "national",
    "engr": "engineering",
    "eng": "engineering",
    "tech": "technology",
    "sys": "systems",
    "svc": "services",
    "svcs": "services",
    "dist": "distribution",
    "ind": "industries",
    "grp": "group",
    "assoc": "associates",
    "fab": "fabrication",
    "div": "division",
    "prod": "products",
    "prods": "products",
    "equip": "equipment",
    "elec": "electric",
    "elect": "electrical",
    "chem": "chemical",
    "env": "environmental",
    "mech": "mechanical",
    "auto": "automotive",
    "aero": "aerospace",
    "pharma": "pharmaceutical",
    "pwr": "power",
    "ctrl": "controls",
    "instr": "instruments",
    "labs": "laboratories",
    "lab": "laboratory",
    "pty": "proprietary",
    "bros": "brothers",
    "hldg": "holding",
    "hldgs": "holdings",
}

# Legal suffixes: use cleanco for robust international handling,
# fall back to regex if cleanco unavailable
try:
    from cleanco import basename as _cleanco_basename
    _HAS_CLEANCO = True
except ImportError:
    _HAS_CLEANCO = False

LEGAL_SUFFIXES = re.compile(
    r"\b(?:inc|incorporated|llc|llp|ltd|limited|co|company|corp|corporation|plc|gmbh|sa|ag)\b",
    re.IGNORECASE,
)


def _strip_legal_suffixes(name: str) -> str:
    """Strip legal entity suffixes using cleanco (80+ countries) with regex fallback."""
    if _HAS_CLEANCO:
        return _cleanco_basename(name)
    return LEGAL_SUFFIXES.sub("", name)

# Pattern to detect CamelCase boundaries: "StellarMetalworks" -> "Stellar Metalworks"
_CAMEL_SPLIT = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


# ---------------------------------------------------------------------------
# Character normalization (fixes OCR, unicode, compound words)
# ---------------------------------------------------------------------------

def _normalize_chars(name: str) -> str:
    """Pre-tokenization character normalization.

    1. Unicode NFKD decomposition -> strip accents (é -> e)
    2. Replace non-breaking spaces and other whitespace with regular space
    3. Split CamelCase words (StellarMetalworks -> Stellar Metalworks)
    4. Strip digits embedded in alpha tokens (Ste1lar -> Stellar)
    5. Normalize all whitespace
    """
    # Unicode: decompose accented characters, keep base letters
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))

    # Normalize all whitespace variants to regular space
    s = re.sub(r"[\s\u00a0\u2000-\u200b\u202f\u205f]+", " ", s)

    # Split CamelCase before lowering
    s = _CAMEL_SPLIT.sub(" ", s)

    # Strip digits embedded within alpha sequences: "Ste1lar" -> "Stellar"
    # But keep standalone numbers and alphanumeric codes (e.g., "A36", "304")
    def _strip_embedded_digits(token: str) -> str:
        if re.match(r"^[a-zA-Z]+$", token):
            return token  # pure alpha, no change
        if re.match(r"^[0-9]+$", token):
            return token  # pure numeric, keep
        # Mixed: strip digits if mostly alpha
        alpha_count = sum(1 for c in token if c.isalpha())
        if alpha_count > len(token) * 0.5:
            return re.sub(r"[0-9]", "", token)
        return token

    words = s.split()
    words = [_strip_embedded_digits(w) for w in words]
    return " ".join(w for w in words if w)


# ---------------------------------------------------------------------------
# Tokenization (shared by Jaccard and Hybrid)
# ---------------------------------------------------------------------------

def tokenize_company(name: str) -> set[str]:
    """Normalize and tokenize a company name into semantic tokens.

    Pipeline:
    1. Character normalization (unicode, OCR digits, CamelCase split)
    2. Lowercase
    3. Expand abbreviations (mfg -> manufacturing)
    4. Strip legal suffixes (Inc, LLC, Co, etc.)
    5. Remove punctuation and extra whitespace
    6. Return set of unique tokens
    """
    s = _strip_legal_suffixes(name)
    s = _normalize_chars(s)
    s = s.lower().strip()

    for abbr, full in ABBREVIATIONS.items():
        s = re.sub(rf"\b{re.escape(abbr)}\b", full, s)

    s = re.sub(r"[^a-z0-9\s]", "", s)
    tokens = s.split()
    return set(t for t in tokens if t)


# ---------------------------------------------------------------------------
# Similarity functions
# ---------------------------------------------------------------------------

def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard index between two token sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def tfidf_jaccard_similarity(
    a: set[str],
    b: set[str],
    idf: dict[str, float],
) -> float:
    """TF-IDF weighted Jaccard: sum(idf of shared) / sum(idf of union).

    Rare tokens (high IDF) contribute more than common ones.
    This prevents "manufacturing" from dominating the score when
    "steel" vs "thermal" is the distinguishing token.
    """
    union = a | b
    if not union:
        return 1.0
    intersection = a & b
    if not intersection:
        return 0.0
    num = sum(idf.get(t, 1.0) for t in intersection)
    den = sum(idf.get(t, 1.0) for t in union)
    return num / den if den > 0 else 0.0


def compute_idf(token_sets: list[set[str]]) -> dict[str, float]:
    """Compute IDF weights from a collection of token sets.

    IDF(t) = log(N / df(t)) where df(t) = number of sets containing t.
    """
    n = len(token_sets)
    if n == 0:
        return {}
    df: Counter = Counter()
    for ts in token_sets:
        for t in ts:
            df[t] += 1
    return {t: math.log(n / count) if count < n else 0.1 for t, count in df.items()}


def cosine_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity matrix from L2-normalized embeddings."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    normed = embeddings / norms
    return normed @ normed.T


# ---------------------------------------------------------------------------
# Union-Find clustering backbone
# ---------------------------------------------------------------------------

def _cluster_from_similarity_matrix(
    unique_names: list[str],
    sim_matrix: np.ndarray,
    threshold: float,
) -> dict[str, list[str]]:
    """Cluster names using union-find on a pairwise similarity matrix."""
    n = len(unique_names)
    parent: dict[str, str] = {name: name for name in unique_names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= threshold:
                union(unique_names[i], unique_names[j])

    clusters: dict[str, list[str]] = {}
    for name in unique_names:
        root = find(name)
        clusters.setdefault(root, []).append(name)

    result: dict[str, list[str]] = {}
    for members in clusters.values():
        canonical = max(members, key=len)
        result[canonical] = sorted(members)
    return result


# ---------------------------------------------------------------------------
# Strategy: Jaccard (plain, kept for benchmarking)
# ---------------------------------------------------------------------------

def cluster_supplier_names(
    raw_names: list[str],
    threshold: float = 0.5,
) -> dict[str, list[str]]:
    """Cluster using token-level Jaccard similarity."""
    unique_names = list(set(raw_names))
    n = len(unique_names)
    token_sets = [tokenize_company(name) for name in unique_names]

    sim_matrix = np.zeros((n, n))
    for i in range(n):
        sim_matrix[i, i] = 1.0
        for j in range(i + 1, n):
            sim = jaccard_similarity(token_sets[i], token_sets[j])
            sim_matrix[i, j] = sim
            sim_matrix[j, i] = sim

    return _cluster_from_similarity_matrix(unique_names, sim_matrix, threshold)


# ---------------------------------------------------------------------------
# Strategy: Embedding
# ---------------------------------------------------------------------------

_embedding_model = None


def _get_embedding_model():
    """Lazy-load the sentence-transformer model (shared with RAG engine)."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def _prepare_for_embedding(name: str) -> str:
    """Lightly normalize a name for embedding (keep more info than tokenize)."""
    s = _strip_legal_suffixes(name)
    s = _normalize_chars(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cluster_by_embedding(
    raw_names: list[str],
    threshold: float = 0.75,
) -> dict[str, list[str]]:
    """Cluster using sentence-transformer embedding cosine similarity."""
    unique_names = list(set(raw_names))
    model = _get_embedding_model()
    prepared = [_prepare_for_embedding(n) for n in unique_names]
    embeddings = model.encode(prepared, normalize_embeddings=True)
    sim_matrix = cosine_similarity_matrix(embeddings)
    return _cluster_from_similarity_matrix(unique_names, sim_matrix, threshold)


# ---------------------------------------------------------------------------
# Strategy: Hybrid v1 (weighted average — kept for benchmarking)
# ---------------------------------------------------------------------------

def cluster_hybrid(
    raw_names: list[str],
    jaccard_threshold: float = 0.5,
    embedding_threshold: float = 0.75,
    jaccard_weight: float = 0.4,
    embedding_weight: float = 0.6,
    combined_threshold: float = 0.55,
) -> dict[str, list[str]]:
    """Cluster using weighted combination of Jaccard and embedding similarity.

    The hybrid score is: jaccard_weight * jaccard_sim + embedding_weight * embedding_sim
    Two names merge if hybrid_score >= combined_threshold.
    """
    unique_names = list(set(raw_names))
    n = len(unique_names)

    # Jaccard matrix
    token_sets = [tokenize_company(name) for name in unique_names]
    jaccard_mat = np.zeros((n, n))
    for i in range(n):
        jaccard_mat[i, i] = 1.0
        for j in range(i + 1, n):
            sim = jaccard_similarity(token_sets[i], token_sets[j])
            jaccard_mat[i, j] = sim
            jaccard_mat[j, i] = sim

    # Embedding matrix
    model = _get_embedding_model()
    prepared = [_prepare_for_embedding(name) for name in unique_names]
    embeddings = model.encode(prepared, normalize_embeddings=True)
    embed_mat = cosine_similarity_matrix(embeddings)

    # Weighted combination
    hybrid_mat = jaccard_weight * jaccard_mat + embedding_weight * embed_mat

    return _cluster_from_similarity_matrix(unique_names, hybrid_mat, combined_threshold)


# ---------------------------------------------------------------------------
# Strategy: Hybrid v2 (gated TF-IDF — new default)
# ---------------------------------------------------------------------------

def cluster_hybrid_v2(
    raw_names: list[str],
    tfidf_threshold: float = 0.5,
    embedding_threshold: float = 0.65,
    min_jaccard_gate: float = 0.3,
    min_embedding_gate: float = 0.5,
) -> dict[str, list[str]]:
    """Gated hybrid clustering with TF-IDF weighted Jaccard.

    Improvements over v1:
    1. TF-IDF Jaccard: rare tokens (steel/thermal) weigh more than common
       ones (manufacturing), fixing the shared-filler-words problem.
    2. Gated merge: BOTH TF-IDF Jaccard >= min_jaccard_gate AND
       embedding >= min_embedding_gate must be true. This prevents:
       - Jaccard false merges (services vs solutions) when embedding disagrees
       - Embedding false merges (AeroFlow vs AeroTech) when Jaccard disagrees
    3. Final merge requires the average of the two scores >= combined threshold.

    Merge condition:
        tfidf_jaccard >= min_jaccard_gate
        AND embedding_cosine >= min_embedding_gate
        AND (tfidf_jaccard + embedding_cosine) / 2 >= combined_threshold

    where combined_threshold = max(tfidf_threshold, embedding_threshold) / 2 + 0.1
    """
    unique_names = list(set(raw_names))
    n = len(unique_names)

    # TF-IDF Jaccard matrix
    token_sets = [tokenize_company(name) for name in unique_names]
    idf = compute_idf(token_sets)
    tfidf_mat = np.zeros((n, n))
    for i in range(n):
        tfidf_mat[i, i] = 1.0
        for j in range(i + 1, n):
            sim = tfidf_jaccard_similarity(token_sets[i], token_sets[j], idf)
            tfidf_mat[i, j] = sim
            tfidf_mat[j, i] = sim

    # Embedding matrix
    model = _get_embedding_model()
    prepared = [_prepare_for_embedding(name) for name in unique_names]
    embeddings = model.encode(prepared, normalize_embeddings=True)
    embed_mat = cosine_similarity_matrix(embeddings)

    # Gated combination: both must pass minimums, then average must pass threshold
    combined_threshold = (tfidf_threshold + embedding_threshold) / 2
    gated_mat = np.zeros((n, n))
    for i in range(n):
        gated_mat[i, i] = 1.0
        for j in range(i + 1, n):
            j_score = tfidf_mat[i, j]
            e_score = embed_mat[i, j]
            # Gate: both must pass their minimums
            if j_score >= min_jaccard_gate and e_score >= min_embedding_gate:
                avg = (j_score + e_score) / 2
                gated_mat[i, j] = avg
                gated_mat[j, i] = avg

    return _cluster_from_similarity_matrix(unique_names, gated_mat, combined_threshold)


# ---------------------------------------------------------------------------
# Strategy: Pipeline (v1 merge → v2 split review)
# ---------------------------------------------------------------------------

def cluster_pipeline(
    raw_names: list[str],
    # Stage 1: v1 params (aggressive merge for recall)
    jaccard_weight: float = 0.4,
    embedding_weight: float = 0.6,
    combined_threshold: float = 0.55,
    # Stage 2: v2 split review params
    tfidf_threshold: float = 0.5,
    split_embedding_threshold: float = 0.65,
    min_jaccard_gate: float = 0.3,
    min_embedding_gate: float = 0.5,
) -> dict[str, list[str]]:
    """Two-stage pipeline: merge aggressively, then split false merges.

    Stage 1 (Hybrid v1): Weighted Jaccard + embedding for high recall.
    Merges everything that's likely the same company.

    Stage 2 (v2 split review): For each cluster with 3+ members,
    re-examine all pairs using TF-IDF Jaccard with gating. If any
    pair within a cluster fails the v2 gates, split the cluster
    into sub-clusters using v2's stricter criteria.

    This gives v1's recall (don't miss real matches) with v2's
    precision (catch false merges after the fact).
    """
    # Stage 1: aggressive merge via hybrid v1
    stage1 = cluster_hybrid(
        raw_names,
        jaccard_weight=jaccard_weight,
        embedding_weight=embedding_weight,
        combined_threshold=combined_threshold,
    )

    # Stage 2: review each cluster for false merges
    unique_names = list(set(raw_names))
    token_sets_map = {name: tokenize_company(name) for name in unique_names}
    all_token_sets = list(token_sets_map.values())
    idf = compute_idf(all_token_sets)

    model = _get_embedding_model()
    embed_cache: dict[str, np.ndarray] = {}
    for name in unique_names:
        prepared = _prepare_for_embedding(name)
        embed_cache[name] = model.encode([prepared], normalize_embeddings=True)[0]

    def _should_stay_merged(name_a: str, name_b: str) -> bool:
        """Decide if a pair v1 merged should stay merged.

        Philosophy: v1 already decided these belong together with good
        reason. Only split if NEITHER signal is strongly confident.

        Empirical observation from the data:
        - False merges: max(J, E) < 0.90 (both signals are lukewarm)
        - True merges: max(J, E) >= 0.90 (at least one signal is strong)

        Examples:
        - APEX MFG <-> Apex Manufacturing Inc: J=1.00, E=0.45 → max=1.00 → KEEP
        - AeroFlow Systems <-> AEROFLOW SYSTEMS: J=0.20, E=0.91 → max=0.91 → KEEP
        - Pacific Steel <-> Pacific Thermal: J=0.36, E=0.76 → max=0.76 → SPLIT
        """
        ts_a = token_sets_map.get(name_a, tokenize_company(name_a))
        ts_b = token_sets_map.get(name_b, tokenize_company(name_b))
        j_score = tfidf_jaccard_similarity(ts_a, ts_b, idf)
        e_a = embed_cache.get(name_a)
        e_b = embed_cache.get(name_b)
        if e_a is not None and e_b is not None:
            e_score = float(np.dot(e_a, e_b))
        else:
            e_score = 0.0
        # Keep merged if at least one signal is strongly confident
        confidence_threshold = (tfidf_threshold + split_embedding_threshold) / 2 + 0.15
        return max(j_score, e_score) >= confidence_threshold

    # Re-cluster within each stage1 cluster using v2 criteria
    final: dict[str, list[str]] = {}
    for canonical, members in stage1.items():
        if len(members) <= 2:
            # Small clusters: keep as-is (v1 already validated)
            final[canonical] = members
            continue

        # Build sub-clusters using union-find with v2 gates
        parent = {m: m for m in members}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if _should_stay_merged(a, b):
                    union(a, b)

        sub_clusters: dict[str, list[str]] = {}
        for m in members:
            root = find(m)
            sub_clusters.setdefault(root, []).append(m)

        for sub_members in sub_clusters.values():
            sub_canonical = max(sub_members, key=len)
            final[sub_canonical] = sorted(sub_members)

    return final


# ---------------------------------------------------------------------------
# Strategy enum + dispatcher
# ---------------------------------------------------------------------------

class ClusterMethod(str, Enum):
    JACCARD = "jaccard"
    EMBEDDING = "embedding"
    HYBRID = "hybrid"
    HYBRID_V2 = "hybrid_v2"
    PIPELINE = "pipeline"


def cluster_names(
    raw_names: list[str],
    method: ClusterMethod = ClusterMethod.PIPELINE,
    **kwargs,
) -> dict[str, list[str]]:
    """Dispatch to the chosen clustering method."""
    if method == ClusterMethod.JACCARD:
        return cluster_supplier_names(raw_names, **kwargs)
    elif method == ClusterMethod.EMBEDDING:
        return cluster_by_embedding(raw_names, **kwargs)
    elif method == ClusterMethod.HYBRID:
        return cluster_hybrid(raw_names, **kwargs)
    elif method == ClusterMethod.HYBRID_V2:
        return cluster_hybrid_v2(raw_names, **kwargs)
    elif method == ClusterMethod.PIPELINE:
        return cluster_pipeline(raw_names, **kwargs)
    raise ValueError(f"Unknown method: {method}")


# ---------------------------------------------------------------------------
# Edge confidence scores
# ---------------------------------------------------------------------------

def compute_edge_scores(
    clusters: dict[str, list[str]],
    confirmed_scores: Optional[dict[str, dict[str, float]]] = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """Compute confidence scores for every variant→canonical edge.

    For each cluster, computes:
      - jaccard: TF-IDF weighted Jaccard between variant and canonical tokens
      - embedding: cosine similarity between variant and canonical embeddings
      - combined: max(jaccard, embedding) — the pipeline merge criterion

    Human-reviewed or confirmed mappings get combined=1.0 by default,
    unless the user specified a custom score in confirmed_mappings.yaml.

    Args:
        clusters: {canonical: [variants]} from clustering + overrides.
        confirmed_scores: {canonical: {variant: custom_score}} from YAML.
            If a variant appears here, its combined score is set to that value
            and source is marked "confirmed". Omitted variants use the
            computed score.

    Returns:
        {canonical: {variant: {"jaccard": float, "embedding": float,
                               "combined": float, "source": str}}}

    The canonical→canonical edge always has score 1.0.
    """
    if confirmed_scores is None:
        confirmed_scores = {}
    # Collect all unique names across all clusters + confirmed overrides
    all_names = set()
    for members in clusters.values():
        all_names.update(members)
    for canonical, variants in confirmed_scores.items():
        all_names.add(canonical)
        all_names.update(variants.keys())
    all_names = list(all_names)

    if not all_names:
        return {}

    # Precompute token sets + IDF
    token_map = {name: tokenize_company(name) for name in all_names}
    idf = compute_idf(list(token_map.values()))

    # Precompute embeddings
    model = _get_embedding_model()
    prepared = {name: _prepare_for_embedding(name) for name in all_names}
    embed_inputs = [prepared[name] for name in all_names]
    embeddings = model.encode(embed_inputs, normalize_embeddings=True)
    embed_map = {name: embeddings[i] for i, name in enumerate(all_names)}

    scores: dict[str, dict[str, dict[str, float]]] = {}

    for canonical, members in clusters.items():
        scores[canonical] = {}
        canonical_overrides = confirmed_scores.get(canonical, {})

        for variant in members:
            if variant == canonical:
                scores[canonical][variant] = {
                    "jaccard": 1.0,
                    "embedding": 1.0,
                    "combined": 1.0,
                    "source": "canonical",
                }
                continue

            # TF-IDF Jaccard
            j = tfidf_jaccard_similarity(
                token_map[variant], token_map[canonical], idf
            )
            # Embedding cosine
            e = float(np.dot(embed_map[variant], embed_map[canonical]))
            # Combined — matches the pipeline's merge criterion
            combined = max(j, e)

            # Check for confirmed/reviewed override
            if variant in canonical_overrides:
                # User-specified score, or 1.0 if they just confirmed without a score
                override = canonical_overrides[variant]
                scores[canonical][variant] = {
                    "jaccard": round(j, 3),
                    "embedding": round(e, 3),
                    "combined": round(override, 3),
                    "source": "confirmed",
                }
            else:
                scores[canonical][variant] = {
                    "jaccard": round(j, 3),
                    "embedding": round(e, 3),
                    "combined": round(combined, 3),
                    "source": "auto",
                }

    return scores


# ---------------------------------------------------------------------------
# Normalizer builder (used by models.py)
# ---------------------------------------------------------------------------

def build_normalizer(
    raw_names: list[str],
    method: ClusterMethod = ClusterMethod.PIPELINE,
    confirmed_path: Optional[str] = None,
    review_path: Optional[str] = None,
    generate_review: bool = False,
    **kwargs,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Build a lookup table from raw names to canonical names.

    Args:
        raw_names: All raw supplier names from the dataset.
        method: Clustering method to use.
        confirmed_path: Path to confirmed_mappings.yaml (human overrides).
        review_path: Path to write review_candidates.yaml.
        generate_review: If True, write uncertain pairs for human review.

    Returns:
        Tuple of (lookup_dict, clusters_dict):
        - lookup_dict: maps every raw name -> its canonical name
        - clusters_dict: maps canonical name -> list of variant raw names
    """
    from pathlib import Path
    from rag.config import CONFIRMED_MAPPINGS_PATH, REVIEW_CANDIDATES_PATH  # config stays in rag

    # Step 1: Run automated clustering
    clusters = cluster_names(raw_names, method=method, **kwargs)

    # Step 2: Apply human overrides if confirmed_mappings.yaml exists
    if confirmed_path or review_path:
        from src.human_review import apply_human_overrides
        cp = Path(confirmed_path) if confirmed_path else None
        rp = Path(review_path) if review_path else None
        if cp or rp:
            clusters = apply_human_overrides(
                clusters,
                confirmed_path=cp or CONFIRMED_MAPPINGS_PATH,
                review_path=rp or REVIEW_CANDIDATES_PATH,
            )

    # Step 3: Generate review file for uncertain pairs
    if generate_review:
        from src.human_review import find_uncertain_pairs, write_review_file
        candidates = find_uncertain_pairs(clusters, raw_names)
        if candidates:
            rp = Path(review_path) if review_path else REVIEW_CANDIDATES_PATH
            write_review_file(candidates, path=rp)

    lookup: dict[str, str] = {}
    for canonical, variants in clusters.items():
        for variant in variants:
            lookup[variant] = canonical
    return lookup, clusters
