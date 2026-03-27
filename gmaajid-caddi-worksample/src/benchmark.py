"""Benchmarking: run resolution pipeline against ground truth scenarios
and compute precision/recall metrics by difficulty tier and category."""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


@dataclass
class BenchmarkResult:
    input_name: str
    expected_canonical: str
    resolved_canonical: Optional[str]
    was_resolved: bool
    difficulty: int
    category: str = ""
    source: str = ""


def compute_metrics(results: list[BenchmarkResult]) -> dict:
    if not results:
        return {
            "overall": {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                        "total": 0, "resolved": 0, "correct": 0},
            "by_tier": {},
            "by_category": {},
        }

    def _calc(subset: list[BenchmarkResult]) -> dict:
        total = len(subset)
        resolved = [r for r in subset if r.was_resolved]
        correct = [r for r in resolved if r.resolved_canonical == r.expected_canonical]
        p = len(correct) / len(resolved) if resolved else 0.0
        r = len(correct) / total if total else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "total": total,
            "resolved": len(resolved),
            "correct": len(correct),
        }

    overall = _calc(results)

    by_tier: dict[int, dict] = {}
    tiers = defaultdict(list)
    for r in results:
        tiers[r.difficulty].append(r)
    for tier in sorted(tiers.keys()):
        by_tier[tier] = _calc(tiers[tier])

    by_category: dict[str, dict] = {}
    categories = defaultdict(list)
    for r in results:
        if r.category:
            categories[r.category].append(r)
    for cat in sorted(categories.keys()):
        by_category[cat] = _calc(categories[cat])

    return {"overall": overall, "by_tier": by_tier, "by_category": by_category}
