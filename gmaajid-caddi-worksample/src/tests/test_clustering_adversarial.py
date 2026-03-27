"""Adversarial worst-case scenarios for supplier name clustering.

These tests are DIAGNOSTIC — they expose the limits of each method rather
than gating on pass/fail. The leaderboard test at the end summarizes
all results for comparison.

Tests combinations of:
- Misspellings + abbreviations together
- Corrupted/garbled text (OCR-like errors, missing chars, swapped chars)
- Names with lots of shared filler words that are actually different companies
- Minimal distinguishing information
- Unicode/encoding artifacts
- Very short and very long names
"""

from __future__ import annotations

import pytest

from src.supplier_clustering import (
    ClusterMethod,
    cluster_names,
)

METHODS = [ClusterMethod.JACCARD, ClusterMethod.EMBEDDING, ClusterMethod.HYBRID, ClusterMethod.HYBRID_V2, ClusterMethod.PIPELINE]


def evaluate(ground_truth: dict[str, list[str]], method: ClusterMethod, **kwargs):
    all_names = []
    name_to_group = {}
    for label, variants in ground_truth.items():
        all_names.extend(variants)
        for v in variants:
            name_to_group[v] = label

    clusters = cluster_names(all_names, method=method, **kwargs)
    name_to_cluster = {}
    for canonical, members in clusters.items():
        for m in members:
            name_to_cluster[m] = canonical

    tp = fp = fn = tn = 0
    names = list(name_to_group.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            same_group = name_to_group[names[i]] == name_to_group[names[j]]
            same_cluster = name_to_cluster.get(names[i]) == name_to_cluster.get(names[j])
            if same_group and same_cluster:
                tp += 1
            elif not same_group and same_cluster:
                fp += 1
            elif same_group and not same_cluster:
                fn += 1
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "n_clusters": len(clusters), "n_expected": len(ground_truth),
        "clusters": {c: sorted(m) for c, m in clusters.items()},
    }


def print_comparison(scenario: str, ground_truth: dict[str, list[str]]):
    print(f"\n  === {scenario} ===")
    print(f"  Expected {len(ground_truth)} groups:")
    for label, variants in ground_truth.items():
        print(f"    {label}: {variants}")

    print(f"\n  {'Method':<12} {'P':>8} {'R':>8} {'F1':>8} {'Clusters':>9} {'TP':>5} {'FP':>5} {'FN':>5}")
    for method in METHODS:
        m = evaluate(ground_truth, method)
        print(f"  {method.value:<12} {m['precision']:>8.1%} {m['recall']:>8.1%} {m['f1']:>8.1%} {m['n_clusters']:>9} {m['tp']:>5} {m['fp']:>5} {m['fn']:>5}")
        if m["fp"] > 0 or m["fn"] > 0:
            print(f"    Clusters: {m['clusters']}")


# ---------------------------------------------------------------------------
# Scenario 1: Misspellings + abbreviations combined
# ---------------------------------------------------------------------------
MISSPELL_ABBREV = {
    "Apex Manufacturing": [
        "APEX MFG",              # abbreviation
        "Apex Manufcturing",     # misspelling
        "APEXMFG",               # no space + abbreviation
        "Apex Manufacturng Inc", # misspelling + suffix
        "APX Manufacturing",     # truncated first word
    ],
    "Apex Farms": [
        "Apex Farms",
        "APEX FARMS LLC",
        "Apex Frams",            # transposed letters
    ],
}


def test_misspell_plus_abbreviation():
    """Misspelling + abbreviation combined. Known hard case."""
    print_comparison("Misspellings + Abbreviations", MISSPELL_ABBREV)
    # All methods struggle here; just verify no false merges (farms != manufacturing)
    for method in METHODS:
        m = evaluate(MISSPELL_ABBREV, method)
        assert m["precision"] >= 0.80, f"{method.value}: merged farms with manufacturing"


# ---------------------------------------------------------------------------
# Scenario 2: OCR-like corruption (missing chars, substitutions)
# ---------------------------------------------------------------------------
OCR_CORRUPTED = {
    "Stellar Metalworks": [
        "Stellar Metalworks",
        "Ste1lar Metalworks",    # 1 for l (OCR)
        "StellarMetalworks",     # no space
        "Stellar Metal works",   # extra space
        "Stellar Metalwork",     # truncated s
    ],
    "Stellar Dynamics": [
        "Stellar Dynamics",
        "Ste1lar Dynamics",      # same OCR pattern
        "Stellar Dynamcs",       # missing i
    ],
}


def test_ocr_corruption():
    """OCR errors: digit substitution, missing spaces, truncation."""
    print_comparison("OCR-Like Corruption", OCR_CORRUPTED)
    # Verify Metalworks and Dynamics stay separate
    for method in METHODS:
        m = evaluate(OCR_CORRUPTED, method)
        assert m["precision"] >= 0.80, f"{method.value}: merged Metalworks with Dynamics"


# ---------------------------------------------------------------------------
# Scenario 3: Heavy shared filler words
# Names that share many common words but are different companies
# ---------------------------------------------------------------------------
SHARED_FILLER = {
    "Pacific Steel Manufacturing": [
        "Pacific Steel Manufacturing Inc",
        "Pacific Steel Mfg Co",
        "Pacific Steel Manufacturing LLC",
    ],
    "Pacific Thermal Manufacturing": [
        "Pacific Thermal Manufacturing Inc",
        "Pacific Thermal Mfg Co",
        "Pacific Thermal Manufacturing LLC",
    ],
    "Atlantic Steel Manufacturing": [
        "Atlantic Steel Manufacturing Inc",
        "Atlantic Steel Mfg Co",
        "Atlantic Steel Manufacturing Corp",
    ],
    "Atlantic Thermal Manufacturing": [
        "Atlantic Thermal Manufacturing Inc",
        "Atlantic Thermal Mfg Co",
    ],
}


def test_shared_filler_words():
    """4 companies sharing 'Manufacturing/Mfg', 'Inc/Co/LLC' — only middle word differs.

    Known weakness: Jaccard gives high similarity because 'manufacturing' dominates
    the 3-token set ({pacific/atlantic, steel/thermal, manufacturing}).
    Jaccard('Pacific Steel Mfg', 'Pacific Thermal Mfg') = 2/3 = 0.67 > 0.5 threshold.
    """
    print_comparison("Heavy Shared Filler Words", SHARED_FILLER)
    # Embedding should do best here since it understands "steel" != "thermal"
    emb = evaluate(SHARED_FILLER, ClusterMethod.EMBEDDING)
    assert emb["n_clusters"] >= 3, "Embedding should find at least 3 distinct clusters"


# ---------------------------------------------------------------------------
# Scenario 4: Minimal distinguishing info (single character difference)
# ---------------------------------------------------------------------------
MINIMAL_DIFF = {
    "ABC Corp A": [
        "ABC Manufacturing - Division A",
        "ABC Mfg Div A",
        "ABC Manufacturing (A)",
    ],
    "ABC Corp B": [
        "ABC Manufacturing - Division B",
        "ABC Mfg Div B",
        "ABC Manufacturing (B)",
    ],
}


def test_minimal_distinguishing_info():
    """Two divisions of same parent differing only by a single letter.

    This is genuinely pathological — 'A' vs 'B' is the only distinguishing token
    in a 3-token set, and single characters are often stripped as noise.
    All methods are expected to struggle.
    """
    print_comparison("Minimal Distinguishing Info", MINIMAL_DIFF)
    for method in METHODS:
        m = evaluate(MINIMAL_DIFF, method)
        print(f"    {method.value}: clusters={m['clusters']}")
    # No assertion — this is a known impossible case, documented for awareness


# ---------------------------------------------------------------------------
# Scenario 5: Extra long names with noise
# ---------------------------------------------------------------------------
LONG_NOISY = {
    "QuickFab Industries": [
        "QuickFab Industries",
        "QuickFab Industries - Authorized Distributor North America",
        "QUICKFAB INDUSTRIES (FORMERLY RAPID FABRICATION CO)",
        "QuickFab Ind. dba Quick Fabrication",
    ],
    "QuickFab Solutions": [
        "QuickFab Solutions",
        "QuickFab Solutions - Engineering Services Division",
        "QUICKFAB SOLUTIONS LLC",
    ],
}


def test_long_noisy_names():
    """Long names with parenthetical notes, DBA clauses, and extra descriptors."""
    print_comparison("Long Noisy Names", LONG_NOISY)
    # Embedding should handle these best (understands semantic similarity despite noise)
    emb = evaluate(LONG_NOISY, ClusterMethod.EMBEDDING)
    assert emb["precision"] >= 0.50, f"Embedding P={emb['precision']:.2%} on long noisy names"


# ---------------------------------------------------------------------------
# Scenario 6: Mixed case + unicode artifacts + encoding garbage
# ---------------------------------------------------------------------------
UNICODE_MESS = {
    "AeroFlow Systems": [
        "AeroFlow Systems",
        "AEROFLOW SYSTEMS",
        "Aeroflow\u00a0Systems",   # non-breaking space
        "AeroFlow Sy stems",       # random space inserted
        "A\u00e9roFlow Systems",   # accented e
    ],
    "AeroTech Systems": [
        "AeroTech Systems",
        "AEROTECH SYSTEMS INC",
        "Aero Tech Systems",
    ],
}


def test_unicode_and_encoding():
    """Unicode artifacts: non-breaking spaces, accented characters, split words."""
    print_comparison("Unicode/Encoding Artifacts", UNICODE_MESS)
    # At least one method should keep AeroFlow and AeroTech separate
    results = {m: evaluate(UNICODE_MESS, m) for m in METHODS}
    best_p = max(r["precision"] for r in results.values())
    assert best_p >= 0.50, f"Best precision {best_p:.2%} — all methods merge AeroFlow with AeroTech"


# ---------------------------------------------------------------------------
# Scenario 7: Abbreviation explosion — everything abbreviated differently
# ---------------------------------------------------------------------------
ABBREV_EXPLOSION = {
    "National Engineering Services": [
        "National Engineering Services",
        "NATL ENG SVC",
        "Nat'l Engineering Svcs",
        "National Engr Services Inc",
        "Natl. Eng. Services LLC",
    ],
    "National Engineering Solutions": [
        "National Engineering Solutions",
        "NATL ENG SOLUTIONS",
        "Nat'l Engr Solutions Inc",
    ],
}


def test_abbreviation_explosion():
    """Multiple abbreviations stacked: natl+eng+svc vs natl+eng+solutions.

    Known weakness: after expansion, 'services' vs 'solutions' is the only
    distinguishing token in a 3-token set. Jaccard = 2/4 = 0.5 (borderline).
    """
    print_comparison("Abbreviation Explosion", ABBREV_EXPLOSION)
    # Document the behavior — this is a known edge case
    for method in METHODS:
        m = evaluate(ABBREV_EXPLOSION, method)
        print(f"    {method.value}: {m['n_clusters']} clusters, P={m['precision']:.1%}")


# ---------------------------------------------------------------------------
# Scenario 8: The kitchen sink — real-world worst case
# ---------------------------------------------------------------------------
KITCHEN_SINK = {
    "Apex Manufacturing": [
        "APEX MFG",
        "Apex Manufacturing Inc",
        "Apex Manufcturing",           # misspelling
        "APEX MANUFACTURING CO LTD",   # extra suffixes
        "Apex Mfg - Main Plant",       # extra descriptor
    ],
    "Apex Farms": [
        "Apex Farms LLC",
        "APEX FARMS",
        "Apex Frams Inc",              # misspelling
    ],
    "Apex Fabrication": [
        "Apex Fabrication",
        "APEX FAB INC",
        "Apex Fabrication Services",
    ],
    "Stellar Metalworks": [
        "Stellar Metalworks",
        "STELLAR METALWORKS INC",
        "Stellar Metal Works LLC",     # split word
    ],
    "Stellar Dynamics": [
        "Stellar Dynamics",
        "STELLAR DYNAMICS CORP",
    ],
    "QuickFab Industries": [
        "QuickFab Industries",
        "QUICKFAB IND",
        "Quick Fab Industries LLC",    # split word
        "QuikFab Industries",          # misspelling
    ],
    "TitanForge": [
        "TitanForge LLC",
        "TITANFORGE",
        "Titan Forge Inc",             # split word
    ],
    "TitanSteel": [
        "TitanSteel Corp",
        "TITANSTEEL",
        "Titan Steel LLC",
    ],
}


def test_kitchen_sink():
    """The ultimate stress test combining all adversarial patterns."""
    print_comparison("Kitchen Sink (All Combined)", KITCHEN_SINK)
    results = {}
    for method in METHODS:
        m = evaluate(KITCHEN_SINK, method)
        results[method.value] = m

    best_method = max(results, key=lambda k: results[k]["f1"])
    best_f1 = results[best_method]["f1"]
    print(f"\n  Best method: {best_method} (F1={best_f1:.2%})")

    # Hybrid should be the best or tied for best
    hybrid = results["hybrid"]
    assert hybrid["f1"] >= 0.50, f"Hybrid F1={hybrid['f1']:.2%} below 50% on kitchen sink"


# ---------------------------------------------------------------------------
# Summary: run everything and print a leaderboard
# ---------------------------------------------------------------------------
ALL_ADVERSARIAL = {
    "Misspell+Abbrev": MISSPELL_ABBREV,
    "OCR Corruption": OCR_CORRUPTED,
    "Shared Filler": SHARED_FILLER,
    "Minimal Diff": MINIMAL_DIFF,
    "Long Noisy": LONG_NOISY,
    "Unicode Mess": UNICODE_MESS,
    "Abbrev Explosion": ABBREV_EXPLOSION,
    "Kitchen Sink": KITCHEN_SINK,
}


def test_adversarial_leaderboard():
    """Print a full leaderboard across all adversarial scenarios."""
    print("\n\n  ╔══════════════════════════════════════════════════════════════════════════╗")
    print("  ║              ADVERSARIAL BENCHMARK LEADERBOARD                         ║")
    print("  ╠══════════════════════════════════════════════════════════════════════════╣")

    totals = {m.value: {"p_sum": 0, "r_sum": 0, "f1_sum": 0, "wins": 0} for m in METHODS}

    for scenario_name, ground_truth in ALL_ADVERSARIAL.items():
        n_groups = len(ground_truth)
        n_names = sum(len(v) for v in ground_truth.values())
        print(f"\n  -- {scenario_name} ({n_groups} groups, {n_names} names) --")
        print(f"  {'Method':<12} {'P':>8} {'R':>8} {'F1':>8} {'Clusters':>4}/{n_groups:<4} {'FP':>4} {'FN':>4}")

        scenario_results = {}
        for method in METHODS:
            m = evaluate(ground_truth, method)
            scenario_results[method.value] = m
            totals[method.value]["p_sum"] += m["precision"]
            totals[method.value]["r_sum"] += m["recall"]
            totals[method.value]["f1_sum"] += m["f1"]

        best_f1 = max(r["f1"] for r in scenario_results.values())
        for method in METHODS:
            m = scenario_results[method.value]
            marker = " <-- best" if m["f1"] == best_f1 else ""
            if m["f1"] == best_f1:
                totals[method.value]["wins"] += 1
            print(f"  {method.value:<12} {m['precision']:>8.1%} {m['recall']:>8.1%} {m['f1']:>8.1%} {m['n_clusters']:>4}/{m['n_expected']:<4} {m['fp']:>4} {m['fn']:>4}{marker}")

    n = len(ALL_ADVERSARIAL)
    print(f"\n  ╠══════════════════════════════════════════════════════════════════════════╣")
    print(f"  ║  AVERAGES across {n} adversarial scenarios                               ║")
    print(f"  ╠══════════════════════════════════════════════════════════════════════════╣")
    print(f"  {'Method':<12} {'Avg P':>8} {'Avg R':>8} {'Avg F1':>8} {'Wins':>6}")
    for method in METHODS:
        t = totals[method.value]
        print(f"  {method.value:<12} {t['p_sum']/n:>8.1%} {t['r_sum']/n:>8.1%} {t['f1_sum']/n:>8.1%} {t['wins']:>6}/{n}")
    print("  ╚══════════════════════════════════════════════════════════════════════════╝")
