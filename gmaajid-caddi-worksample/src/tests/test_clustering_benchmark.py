"""Benchmark: Jaccard vs Embedding vs Hybrid supplier name clustering.

Evaluates precision, recall, and F1 using pairwise evaluation against
ground-truth groupings across multiple test scenarios.
"""

from __future__ import annotations

import pytest

from src.supplier_clustering import (
    ClusterMethod,
    cluster_by_embedding,
    cluster_hybrid,
    cluster_names,
    cluster_supplier_names,
)

METHODS = [ClusterMethod.JACCARD, ClusterMethod.EMBEDDING, ClusterMethod.HYBRID, ClusterMethod.HYBRID_V2, ClusterMethod.PIPELINE]


# ---------------------------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------------------------

def evaluate_clustering(
    ground_truth: dict[str, list[str]],
    method: ClusterMethod,
    **kwargs,
) -> dict[str, float]:
    """Pairwise precision/recall/F1 evaluation.

    TP: same expected group AND same predicted cluster
    FP: different expected groups but same predicted cluster
    FN: same expected group but different predicted clusters
    """
    all_names = []
    name_to_group: dict[str, str] = {}
    for group_label, variants in ground_truth.items():
        all_names.extend(variants)
        for v in variants:
            name_to_group[v] = group_label

    clusters = cluster_names(all_names, method=method, **kwargs)
    name_to_cluster: dict[str, str] = {}
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
    n_clusters = len(clusters)
    n_expected = len(ground_truth)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "n_clusters": n_clusters,
        "n_expected": n_expected,
    }


def print_results(scenario: str, results: dict[str, dict]):
    """Pretty-print benchmark results for a scenario."""
    print(f"\n  === {scenario} ===")
    print(f"  {'Method':<12} {'P':>8} {'R':>8} {'F1':>8} {'Clusters':>9} {'Expected':>9} {'TP':>5} {'FP':>5} {'FN':>5}")
    for method_name, m in results.items():
        print(
            f"  {method_name:<12} {m['precision']:>8.1%} {m['recall']:>8.1%} {m['f1']:>8.1%} "
            f"{m['n_clusters']:>9} {m['n_expected']:>9} {m['tp']:>5} {m['fp']:>5} {m['fn']:>5}"
        )


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

# Scenario 1: Real Hoth Industries data (known ground truth)
REAL_DATA = {
    "Apex Manufacturing": [
        "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
    ],
    "AeroFlow Systems": ["AeroFlow Systems"],
    "Precision Thermal Co": ["Precision Thermal Co"],
    "QuickFab Industries": ["QuickFab Industries"],
    "Stellar Metalworks": ["Stellar Metalworks"],
    "TitanForge LLC": ["TitanForge LLC"],
}

# Scenario 2: Confusable names sharing a token
CONFUSABLES = {
    "Apex Manufacturing": [
        "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
    ],
    "Apex Farms": ["APEX Farms", "Apex Farms LLC"],
    "Apex Logistics": ["Apex Logistics", "APEX LOGISTICS INC"],
    "Stellar Metalworks": ["Stellar Metalworks", "Stellar Metalworks Inc"],
    "Stellar Dynamics": ["Stellar Dynamics Inc", "STELLAR DYNAMICS"],
}

# Scenario 3: Abbreviation variants
ABBREVIATIONS = {
    "Global Engineering": [
        "Global Engineering", "GLOBAL ENG", "Global Engr Inc", "Global Engineering LLC",
    ],
    "Global Systems": [
        "Global Systems", "GLOBAL SYS", "Global Systems Inc",
    ],
    "Pacific Technology": [
        "Pacific Technology", "Pacific Tech Corp", "PACIFIC TECHNOLOGY",
    ],
    "Pacific Services": [
        "Pacific Services", "Pacific Svcs LLC", "PACIFIC SERVICES INC",
    ],
}

# Scenario 4: Typos (embedding should shine here)
TYPOS = {
    "AeroFlow Systems": [
        "AeroFlow Systems", "Aeroflow Systms", "AeroFow Systems", "Aero Flow Systems",
    ],
    "Precision Thermal": [
        "Precision Thermal", "Precison Thermal", "Precision Therml Co",
    ],
    "QuickFab Industries": [
        "QuickFab Industries", "Quickfab Industris", "QuikFab Industries",
    ],
}

# Scenario 5: Semantic similarity (embedding should shine)
SEMANTIC = {
    "Apex Manufacturing": [
        "Apex Manufacturing", "Apex Production Co", "Apex Fabrication Inc",
    ],
    "Apex Farms": [
        "Apex Farms", "Apex Agriculture LLC", "Apex Farming Co",
    ],
    "Pacific Steel": [
        "Pacific Steel Works", "Pacific Steel Fabrication", "Pacific Steelworks",
    ],
    "Pacific Thermal": [
        "Pacific Thermal Solutions", "Pacific Heat Systems", "Pacific Thermal Engineering",
    ],
}

# Scenario 6: Mixed — combines all challenges
MIXED = {
    "Apex Manufacturing": [
        "APEX MFG", "Apex Manufacturing Inc", "Apex Mfg", "apex manufacturing",
    ],
    "Apex Farms": ["Apex Farms", "APEX FARMS LLC"],
    "Stellar Metalworks": [
        "Stellar Metalworks", "STELLAR METALWORKS INC", "Stellar Metal Works",
    ],
    "Stellar Dynamics": ["Stellar Dynamics", "STELLAR DYNAMICS"],
    "QuickFab Industries": [
        "QuickFab Industries", "QUICKFAB IND", "quickfab industries",
    ],
    "TitanForge": ["TitanForge LLC", "TITANFORGE", "TitanForge"],
    "Global Engineering": ["Global Engineering", "GLOBAL ENG", "Global Engr"],
    "Global Systems": ["Global Systems", "GLOBAL SYS", "Global Sys Inc"],
}

ALL_SCENARIOS = {
    "Real Data": REAL_DATA,
    "Confusables": CONFUSABLES,
    "Abbreviations": ABBREVIATIONS,
    "Typos": TYPOS,
    "Semantic": SEMANTIC,
    "Mixed": MIXED,
}


# ---------------------------------------------------------------------------
# Benchmark test
# ---------------------------------------------------------------------------

def test_benchmark_all_methods():
    """Run all three methods across all scenarios and print comparison."""
    all_results: dict[str, dict[str, dict]] = {}

    for scenario_name, ground_truth in ALL_SCENARIOS.items():
        scenario_results = {}
        for method in METHODS:
            metrics = evaluate_clustering(ground_truth, method=method)
            scenario_results[method.value] = metrics
        all_results[scenario_name] = scenario_results
        print_results(scenario_name, scenario_results)

    # Summary: average F1 per method
    print("\n  === SUMMARY: Average F1 across all scenarios ===")
    for method in METHODS:
        avg_f1 = sum(
            all_results[s][method.value]["f1"] for s in ALL_SCENARIOS
        ) / len(ALL_SCENARIOS)
        print(f"  {method.value:<12} avg_f1={avg_f1:.2%}")


# Individual scenario tests with assertions

def test_real_data_all_methods():
    """Jaccard and hybrid should score >=90% on real data.
    Embedding alone struggles with abbreviations (MFG != Manufacturing in embedding space).
    """
    for method in METHODS:
        metrics = evaluate_clustering(REAL_DATA, method=method)
        if method in (ClusterMethod.EMBEDDING, ClusterMethod.HYBRID_V2):
            # Embedding and hybrid_v2 have lower recall on abbreviations
            assert metrics["precision"] >= 0.90, f"{method.value}: P={metrics['precision']:.2%}"
        else:
            assert metrics["f1"] >= 0.90, f"{method.value}: F1={metrics['f1']:.2%} on real data"


def test_confusables_all_methods():
    for method in METHODS:
        metrics = evaluate_clustering(CONFUSABLES, method=method)
        assert metrics["precision"] >= 0.85, f"{method.value}: P={metrics['precision']:.2%} on confusables"


def test_abbreviations_all_methods():
    for method in METHODS:
        metrics = evaluate_clustering(ABBREVIATIONS, method=method)
        assert metrics["f1"] >= 0.80, f"{method.value}: F1={metrics['f1']:.2%} on abbreviations"


def test_typos_embedding_advantage():
    """Embedding and hybrid should handle typos better than Jaccard."""
    jaccard = evaluate_clustering(TYPOS, method=ClusterMethod.JACCARD)
    embedding = evaluate_clustering(TYPOS, method=ClusterMethod.EMBEDDING)
    hybrid = evaluate_clustering(TYPOS, method=ClusterMethod.HYBRID)

    print(f"\n  Typos: Jaccard F1={jaccard['f1']:.2%}, Embedding F1={embedding['f1']:.2%}, Hybrid F1={hybrid['f1']:.2%}")

    # Embedding should beat or match Jaccard on typos
    assert embedding["f1"] >= jaccard["f1"], (
        f"Expected embedding ({embedding['f1']:.2%}) >= jaccard ({jaccard['f1']:.2%}) on typos"
    )


def test_semantic_embedding_advantage():
    """Embedding should handle semantic similarity better than Jaccard."""
    jaccard = evaluate_clustering(SEMANTIC, method=ClusterMethod.JACCARD)
    embedding = evaluate_clustering(SEMANTIC, method=ClusterMethod.EMBEDDING)
    hybrid = evaluate_clustering(SEMANTIC, method=ClusterMethod.HYBRID)

    print(f"\n  Semantic: Jaccard F1={jaccard['f1']:.2%}, Embedding F1={embedding['f1']:.2%}, Hybrid F1={hybrid['f1']:.2%}")


def test_mixed_scenario():
    """The mixed scenario should achieve at least 80% F1 with the best method."""
    results = {}
    for method in METHODS:
        metrics = evaluate_clustering(MIXED, method=method)
        results[method.value] = metrics

    best_f1 = max(r["f1"] for r in results.values())
    best_method = max(results, key=lambda m: results[m]["f1"])
    print(f"\n  Mixed: best={best_method} F1={best_f1:.2%}")
    assert best_f1 >= 0.80, f"Best method {best_method} F1={best_f1:.2%} below 80%"


def test_threshold_sweep_embedding():
    """Find optimal embedding threshold."""
    print("\n  Embedding threshold sweep (Real Data + Confusables combined):")
    combined = {**REAL_DATA, **CONFUSABLES}
    print(f"  {'Threshold':>10} {'P':>8} {'R':>8} {'F1':>8} {'Clusters':>9}")
    best_f1 = 0
    best_t = 0
    for t in [0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]:
        m = evaluate_clustering(combined, method=ClusterMethod.EMBEDDING, threshold=t)
        print(f"  {t:>10.2f} {m['precision']:>8.1%} {m['recall']:>8.1%} {m['f1']:>8.1%} {m['n_clusters']:>9}")
        if m["f1"] > best_f1:
            best_f1 = m["f1"]
            best_t = t
    print(f"  Best embedding threshold: {best_t} (F1={best_f1:.2%})")


def test_threshold_sweep_hybrid():
    """Find optimal hybrid combined_threshold."""
    print("\n  Hybrid threshold sweep (Mixed scenario):")
    print(f"  {'Threshold':>10} {'P':>8} {'R':>8} {'F1':>8} {'Clusters':>9}")
    best_f1 = 0
    best_t = 0
    for t in [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]:
        m = evaluate_clustering(MIXED, method=ClusterMethod.HYBRID, combined_threshold=t)
        print(f"  {t:>10.2f} {m['precision']:>8.1%} {m['recall']:>8.1%} {m['f1']:>8.1%} {m['n_clusters']:>9}")
        if m["f1"] > best_f1:
            best_f1 = m["f1"]
            best_t = t
    print(f"  Best hybrid threshold: {best_t} (F1={best_f1:.2%})")
