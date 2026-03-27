"""Human-in-the-loop review system for supplier name clustering.

Each review run gets a unique ID (timestamp-based) and its own YAML file
in config/review/. Reviews can be worked on independently and all decisions
are aggregated when applying overrides.

Files:
- config/review/review_YYYYMMDD_HHMMSS.yaml — one per review session
- config/confirmed_mappings.yaml — human-curated permanent overrides
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from src.supplier_clustering import (
    _get_embedding_model,
    _prepare_for_embedding,
    compute_idf,
    cosine_similarity_matrix,
    tfidf_jaccard_similarity,
    tokenize_company,
)

from rag.config import (  # config stays in rag
    CONFIRMED_MAPPINGS_PATH,
    REVIEW_CANDIDATES_PATH,
    REVIEW_DIR,
    REVIEWER_CONFIG_PATH,
)

DEFAULT_REVIEW_DIR = REVIEW_DIR
DEFAULT_CONFIRMED_PATH = CONFIRMED_MAPPINGS_PATH


def load_reviewer(path: Path = REVIEWER_CONFIG_PATH) -> dict[str, str]:
    """Load reviewer identity from config/reviewer.yaml.

    Returns dict with name, email, role. All fields default to empty string
    if the file is missing or fields are blank.
    """
    defaults = {"name": "", "email": "", "role": ""}
    if not path.exists():
        return defaults
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return {k: str(data.get(k, "") or "") for k in defaults}


def _generate_review_id() -> str:
    """Generate a unique review ID based on timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def find_uncertain_pairs(
    clusters: dict[str, list[str]],
    all_raw_names: list[str],
    confidence_low: float = 0.55,
    confidence_high: float = 0.85,
) -> list[dict]:
    """Find pairs where the clustering decision was uncertain.

    Looks for two types of uncertainty:
    1. WITHIN a cluster: pairs where max(tfidf_jaccard, embedding) is low
    2. ACROSS clusters: pairs in different clusters where similarity is high

    Returns list of candidate dicts with scores and suggested action.
    """
    unique_names = list(set(all_raw_names))
    token_sets = {n: tokenize_company(n) for n in unique_names}
    idf = compute_idf(list(token_sets.values()))

    model = _get_embedding_model()
    prepared = {n: _prepare_for_embedding(n) for n in unique_names}
    embeddings = {n: model.encode([prepared[n]], normalize_embeddings=True)[0] for n in unique_names}

    def _scores(a: str, b: str) -> tuple[float, float]:
        j = tfidf_jaccard_similarity(
            token_sets.get(a, tokenize_company(a)),
            token_sets.get(b, tokenize_company(b)),
            idf,
        )
        ea = embeddings.get(a)
        eb = embeddings.get(b)
        e = float(np.dot(ea, eb)) if ea is not None and eb is not None else 0.0
        return j, e

    candidates = []

    # Type 1: Check within clusters for weak pairs
    for canonical, members in clusters.items():
        if len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                j, e = _scores(a, b)
                confidence = max(j, e)
                if confidence < confidence_high:
                    candidates.append({
                        "name_a": a,
                        "name_b": b,
                        "tfidf_jaccard": round(j, 3),
                        "embedding_cosine": round(e, 3),
                        "confidence": round(confidence, 3),
                        "current_action": "merged",
                        "cluster": canonical,
                        "suggested_action": "review_merge",
                        "reason": f"Merged but confidence={confidence:.2f} < {confidence_high:.2f}",
                    })

    # Type 2: Check across clusters for high-similarity splits
    canonicals = list(clusters.keys())
    for i, ca in enumerate(canonicals):
        for cb in canonicals[i + 1:]:
            rep_a = ca
            rep_b = cb
            j, e = _scores(rep_a, rep_b)
            if e >= confidence_low or j >= confidence_low:
                candidates.append({
                    "name_a": rep_a,
                    "name_b": rep_b,
                    "tfidf_jaccard": round(j, 3),
                    "embedding_cosine": round(e, 3),
                    "confidence": round(max(j, e), 3),
                    "current_action": "split",
                    "cluster_a": ca,
                    "cluster_b": cb,
                    "suggested_action": "review_split",
                    "reason": f"Split but similarity={max(j, e):.2f} >= {confidence_low:.2f}",
                })

    candidates.sort(key=lambda c: c["confidence"])
    return candidates


def write_review_file(
    candidates: list[dict],
    path: Optional[Path] = None,
    review_dir: Path = DEFAULT_REVIEW_DIR,
) -> Path:
    """Write uncertain pairs to a YAML file with a unique review ID.

    Each review gets its own file: config/review/review_YYYYMMDD_HHMMSS.yaml
    """
    review_id = _generate_review_id()

    if path is None:
        review_dir.mkdir(parents=True, exist_ok=True)
        path = review_dir / f"review_{review_id}.yaml"

    output = {
        "review_id": review_id,
        "created": datetime.now().isoformat(),
        "status": "pending",
        "reviewed": False,
        "reviewed_at": None,
        "reviewed_by": None,
        "total_pairs": len(candidates),
        "_instructions": (
            "Review each pair below. Edit the 'decision' field:\n"
            "  - 'merge': these are the same company, keep/create the merge\n"
            "  - 'split': these are different companies, keep/create the split\n"
            "  - 'skip': unsure, leave for later\n"
            "Then run 'make ingest' to apply."
        ),
        "pairs": [],
    }
    now = datetime.now().isoformat()
    for i, c in enumerate(candidates):
        pair = {
            "pair_id": f"{review_id}_{i + 1:03d}",
            "name_a": c["name_a"],
            "name_b": c["name_b"],
            "tfidf_jaccard": c["tfidf_jaccard"],
            "embedding_cosine": c["embedding_cosine"],
            "current_action": c["current_action"],
            "reason": c["reason"],
            "decision": c["current_action"],  # auto decision as default
            "decided_by": "auto",
            "decided_at": now,
        }
        output["pairs"].append(pair)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return path


def list_reviews(review_dir: Path = DEFAULT_REVIEW_DIR) -> list[dict]:
    """List all review files with their status summary.

    Returns list of dicts with review_id, path, status, total, decided, pending.
    """
    if not review_dir.exists():
        return []

    reviews = []
    for path in sorted(review_dir.glob("review_*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        pairs = data.get("pairs", [])
        decided = sum(1 for p in pairs if p.get("decision", "skip") != "skip")
        pending = len(pairs) - decided

        reviews.append({
            "review_id": data.get("review_id", path.stem),
            "path": path,
            "created": data.get("created", "unknown"),
            "reviewed": data.get("reviewed", False),
            "reviewed_at": data.get("reviewed_at"),
            "reviewed_by": data.get("reviewed_by"),
            "status": "complete" if pending == 0 and pairs else "pending" if pairs else "empty",
            "total": len(pairs),
            "decided": decided,
            "pending": pending,
        })
    return reviews


def load_confirmed_mappings(
    path: Path = DEFAULT_CONFIRMED_PATH,
) -> dict[str, str]:
    """Load human-confirmed name mappings from YAML.

    Returns dict mapping each raw name -> canonical name.
    """
    if not path.exists():
        return {}

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    lookup: dict[str, str] = {}
    for group in data.get("mappings", []):
        canonical = group["canonical"]
        for name in group.get("names", []):
            lookup[name] = canonical
        lookup[canonical] = canonical
    return lookup


def load_confirmed_scores(
    path: Path = DEFAULT_CONFIRMED_PATH,
) -> dict[str, dict[str, float]]:
    """Load per-variant confidence scores from confirmed_mappings.yaml.

    Supports two formats:
      names: ["A", "B"]           → both get score 1.0 (default)
      names:
        - name: "A"
          score: 0.9             → custom score
        - "B"                    → gets default 1.0

    Returns:
        {canonical: {variant: score}}
    """
    if not path.exists():
        return {}

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    result: dict[str, dict[str, float]] = {}
    default_score = data.get("default_score", 1.0)

    for group in data.get("mappings", []):
        canonical = group["canonical"]
        result[canonical] = {}
        for entry in group.get("names", []):
            if isinstance(entry, str):
                result[canonical][entry] = default_score
            elif isinstance(entry, dict):
                name = entry["name"]
                score = entry.get("score", default_score)
                result[canonical][name] = score
    return result


def load_review_decisions(
    path: Optional[Path] = None,
    review_dir: Path = DEFAULT_REVIEW_DIR,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Load human decisions from review file(s).

    If path is given, reads that single file.
    If path is None, reads ALL review files in review_dir and aggregates.

    Returns:
        (merge_pairs, split_pairs): lists of (name_a, name_b) tuples
    """
    files = []
    if path is not None:
        if path.exists():
            files = [path]
    elif review_dir.exists():
        files = sorted(review_dir.glob("review_*.yaml"))

    merges = []
    splits = []
    for f in files:
        with open(f) as fh:
            data = yaml.safe_load(fh) or {}
        for pair in data.get("pairs", []):
            decision = pair.get("decision", "skip")
            if decision == "merge":
                merges.append((pair["name_a"], pair["name_b"]))
            elif decision == "split":
                splits.append((pair["name_a"], pair["name_b"]))
    return merges, splits


def apply_human_overrides(
    clusters: dict[str, list[str]],
    confirmed_path: Path = DEFAULT_CONFIRMED_PATH,
    review_path: Optional[Path] = None,
    review_dir: Path = DEFAULT_REVIEW_DIR,
) -> dict[str, list[str]]:
    """Apply human overrides to clustering results.

    Priority order:
    1. confirmed_mappings.yaml (explicit canonical assignments)
    2. Review file decisions — reads all files in review_dir if review_path is None
    3. Original clustering (for names not covered by overrides)
    """
    confirmed = load_confirmed_mappings(confirmed_path)
    merge_pairs, split_pairs = load_review_decisions(path=review_path, review_dir=review_dir)

    if not confirmed and not merge_pairs and not split_pairs:
        return clusters

    all_names = []
    for members in clusters.values():
        all_names.extend(members)

    name_to_canonical: dict[str, str] = {}

    # Apply confirmed mappings first (highest priority)
    for name in all_names:
        if name in confirmed:
            name_to_canonical[name] = confirmed[name]

    # Apply original clustering for names not in confirmed
    for canonical, members in clusters.items():
        for name in members:
            if name not in name_to_canonical:
                name_to_canonical[name] = canonical

    # Names locked by confirmed mappings — never override these
    locked = set(name for name in all_names if name in confirmed)

    # Apply merge decisions (only for non-locked names)
    for a, b in merge_pairs:
        if a in name_to_canonical and b in name_to_canonical:
            if a in locked or b in locked:
                continue  # confirmed mappings take precedence
            target = name_to_canonical[a]
            source = name_to_canonical[b]
            for name, canon in list(name_to_canonical.items()):
                if canon == source and name not in locked:
                    name_to_canonical[name] = target

    # Apply split decisions (only for non-locked names)
    for a, b in split_pairs:
        if a in name_to_canonical and b in name_to_canonical:
            if a in locked or b in locked:
                continue
            if name_to_canonical[a] == name_to_canonical[b]:
                name_to_canonical[b] = b

    # Rebuild clusters — use the canonical name from the mapping as the key,
    # not the longest member name (which could collide across groups)
    result: dict[str, list[str]] = {}
    for name, canonical in name_to_canonical.items():
        result.setdefault(canonical, []).append(name)

    final: dict[str, list[str]] = {}
    for canonical, members in result.items():
        final[canonical] = sorted(members)
    return final
