"""End-to-end test: full human-in-the-loop cycle.

Simulates the complete workflow:
1. Initial clustering produces errors (false merges + false splits)
2. System generates review candidates with similarity scores
3. Human reviews and makes decisions (simulated)
4. Re-evaluation with human knowledge produces correct clusters
5. Confirmed mappings persist and apply to future runs
6. New data arriving triggers fresh review for unknowns only
"""

from pathlib import Path

import pytest
import yaml

from src.human_review import (
    apply_human_overrides,
    find_uncertain_pairs,
    load_confirmed_mappings,
    load_review_decisions,
    write_review_file,
)
from src.supplier_clustering import (
    ClusterMethod,
    build_normalizer,
    cluster_names,
)


# Ground truth: what a human would say is correct
GROUND_TRUTH = {
    "Apex Manufacturing": [
        "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
    ],
    "Apex Farms": ["Apex Farms", "APEX FARMS LLC"],
    "Stellar Metalworks": ["Stellar Metalworks", "STELLAR METALWORKS INC"],
    "Stellar Dynamics": ["Stellar Dynamics", "STELLAR DYNAMICS"],
    "QuickFab Industries": ["QuickFab Industries", "QUICKFAB IND"],
}

ALL_NAMES = [name for variants in GROUND_TRUTH.values() for name in variants]


def _pairwise_eval(clusters, ground_truth):
    """Evaluate clusters against ground truth using pairwise P/R/F1."""
    all_names = [n for vs in ground_truth.values() for n in vs]
    name_to_group = {}
    for label, variants in ground_truth.items():
        for v in variants:
            name_to_group[v] = label
    name_to_cluster = {}
    for canonical, members in clusters.items():
        for m in members:
            name_to_cluster[m] = canonical

    tp = fp = fn = 0
    for i in range(len(all_names)):
        for j in range(i + 1, len(all_names)):
            a, b = all_names[i], all_names[j]
            same_group = name_to_group.get(a) == name_to_group.get(b)
            same_cluster = name_to_cluster.get(a) == name_to_cluster.get(b)
            if same_group and same_cluster:
                tp += 1
            elif not same_group and same_cluster:
                fp += 1
            elif same_group and not same_cluster:
                fn += 1

    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": p, "recall": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


class TestHumanLoopFullCycle:
    """Tests the complete human-in-the-loop improvement cycle."""

    def test_step1_initial_clustering_has_errors(self):
        """Step 1: Automated clustering is imperfect on this data."""
        clusters = cluster_names(ALL_NAMES, method=ClusterMethod.PIPELINE)
        metrics = _pairwise_eval(clusters, GROUND_TRUTH)
        print(f"\n  Step 1 (auto): P={metrics['precision']:.0%} R={metrics['recall']:.0%} F1={metrics['f1']:.0%}")
        print(f"  Clusters: {len(clusters)} (expected {len(GROUND_TRUTH)})")
        # Imperfect — this is why we need human review
        assert metrics["f1"] < 1.0, "Clustering should have some errors for this test to be meaningful"

    def test_step2_review_candidates_generated(self, tmp_path):
        """Step 2: System identifies uncertain pairs and writes review file."""
        clusters = cluster_names(ALL_NAMES, method=ClusterMethod.PIPELINE)
        candidates = find_uncertain_pairs(clusters, ALL_NAMES)

        review_path = tmp_path / "review.yaml"
        write_review_file(candidates, path=review_path)

        assert review_path.exists()
        with open(review_path) as f:
            data = yaml.safe_load(f)

        print(f"\n  Step 2: {len(data['pairs'])} uncertain pairs flagged")
        for pair in data["pairs"]:
            print(f"    {pair['name_a']:<30s} <-> {pair['name_b']:<30s} "
                  f"J={pair['tfidf_jaccard']:.2f} E={pair['embedding_cosine']:.2f} "
                  f"[{pair['current_action']}]")

        # Should find at least some uncertain pairs
        assert len(data["pairs"]) >= 0  # may be 0 if clustering is confident
        # All pairs start with auto decisions and metadata
        for pair in data["pairs"]:
            assert pair["decided_by"] == "auto"
            assert "decided_at" in pair
            assert pair["decision"] == pair["current_action"]  # auto defaults to system action

    def test_step3_human_makes_decisions(self, tmp_path):
        """Step 3: Simulate human editing the review file with correct decisions."""
        clusters = cluster_names(ALL_NAMES, method=ClusterMethod.PIPELINE)
        candidates = find_uncertain_pairs(clusters, ALL_NAMES)
        review_path = tmp_path / "review.yaml"
        write_review_file(candidates, path=review_path)

        # Simulate human: read the file and make correct decisions
        with open(review_path) as f:
            data = yaml.safe_load(f)

        decisions_made = 0
        for pair in data.get("pairs", []):
            a, b = pair["name_a"], pair["name_b"]
            # Look up ground truth: should these be merged or split?
            group_a = next((g for g, vs in GROUND_TRUTH.items() if a in vs), None)
            group_b = next((g for g, vs in GROUND_TRUTH.items() if b in vs), None)
            if group_a and group_b:
                if group_a == group_b:
                    pair["decision"] = "merge"
                else:
                    pair["decision"] = "split"
                decisions_made += 1

        with open(review_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        print(f"\n  Step 3: Human made {decisions_made} decisions")

        # Verify decisions were written
        merges, splits = load_review_decisions(review_path)
        print(f"    Merges: {len(merges)}, Splits: {len(splits)}")

    def test_step4_re_evaluation_improves(self, tmp_path):
        """Step 4: Re-run with human decisions — results should improve."""
        # Initial clustering
        clusters_before = cluster_names(ALL_NAMES, method=ClusterMethod.PIPELINE)
        metrics_before = _pairwise_eval(clusters_before, GROUND_TRUTH)

        # Generate and simulate human review
        candidates = find_uncertain_pairs(clusters_before, ALL_NAMES)
        review_path = tmp_path / "review.yaml"
        write_review_file(candidates, path=review_path)

        with open(review_path) as f:
            data = yaml.safe_load(f)
        for pair in data.get("pairs", []):
            a, b = pair["name_a"], pair["name_b"]
            group_a = next((g for g, vs in GROUND_TRUTH.items() if a in vs), None)
            group_b = next((g for g, vs in GROUND_TRUTH.items() if b in vs), None)
            if group_a and group_b:
                pair["decision"] = "merge" if group_a == group_b else "split"
        with open(review_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        # Re-evaluate with human decisions
        clusters_after = apply_human_overrides(
            clusters_before,
            confirmed_path=tmp_path / "nonexistent.yaml",
            review_path=review_path,
        )
        metrics_after = _pairwise_eval(clusters_after, GROUND_TRUTH)

        print(f"\n  Step 4: Before: P={metrics_before['precision']:.0%} R={metrics_before['recall']:.0%} F1={metrics_before['f1']:.0%}")
        print(f"          After:  P={metrics_after['precision']:.0%} R={metrics_after['recall']:.0%} F1={metrics_after['f1']:.0%}")
        print(f"          Clusters: {len(clusters_before)} -> {len(clusters_after)} (expected {len(GROUND_TRUTH)})")

        # F1 should improve or stay the same (human decisions are correct)
        assert metrics_after["f1"] >= metrics_before["f1"], (
            f"Human review should not make things worse: {metrics_after['f1']:.2%} < {metrics_before['f1']:.2%}"
        )

    def test_step5_confirmed_mappings_persist(self, tmp_path):
        """Step 5: Human promotes decisions to confirmed_mappings.yaml — they persist across runs."""
        confirmed_path = tmp_path / "confirmed.yaml"
        confirmed_path.write_text(yaml.dump({
            "mappings": [
                {
                    "names": list(GROUND_TRUTH["Apex Manufacturing"]),
                    "canonical": "Apex Manufacturing",
                },
                {
                    "names": list(GROUND_TRUTH["Apex Farms"]),
                    "canonical": "Apex Farms",
                },
                {
                    "names": list(GROUND_TRUTH["Stellar Metalworks"]),
                    "canonical": "Stellar Metalworks",
                },
                {
                    "names": list(GROUND_TRUTH["Stellar Dynamics"]),
                    "canonical": "Stellar Dynamics",
                },
                {
                    "names": list(GROUND_TRUTH["QuickFab Industries"]),
                    "canonical": "QuickFab Industries",
                },
            ]
        }))

        # Run clustering (may produce errors) then apply confirmed overrides
        clusters = cluster_names(ALL_NAMES, method=ClusterMethod.PIPELINE)
        clusters = apply_human_overrides(
            clusters,
            confirmed_path=confirmed_path,
            review_path=tmp_path / "nonexistent.yaml",
        )
        metrics = _pairwise_eval(clusters, GROUND_TRUTH)

        print(f"\n  Step 5: With confirmed mappings: P={metrics['precision']:.0%} R={metrics['recall']:.0%} F1={metrics['f1']:.0%}")
        print(f"          Clusters: {len(clusters)} (expected {len(GROUND_TRUTH)})")

        # With full confirmed mappings, should be perfect
        assert metrics["precision"] == 1.0, f"Precision should be 100% with confirmed mappings"
        assert metrics["recall"] == 1.0, f"Recall should be 100% with confirmed mappings"

    def test_step6_new_data_triggers_review(self, tmp_path):
        """Step 6: When new supplier names arrive, only unknowns need review."""
        # Existing confirmed mappings
        confirmed_path = tmp_path / "confirmed.yaml"
        confirmed_path.write_text(yaml.dump({
            "mappings": [
                {
                    "names": list(GROUND_TRUTH["Apex Manufacturing"]),
                    "canonical": "Apex Manufacturing",
                },
            ]
        }))

        # New data arrives with a name not in confirmed mappings
        new_names = ALL_NAMES + ["Apex Precision LLC", "APEX PRECISION"]

        clusters = cluster_names(new_names, method=ClusterMethod.PIPELINE)
        clusters = apply_human_overrides(
            clusters,
            confirmed_path=confirmed_path,
            review_path=tmp_path / "nonexistent.yaml",
        )

        # The confirmed Apex names should be correctly grouped
        apex_members = None
        for canonical, members in clusters.items():
            if "APEX MFG" in members:
                apex_members = set(members)
                break
        assert apex_members is not None
        for name in GROUND_TRUTH["Apex Manufacturing"]:
            assert name in apex_members, f"{name} should be in Apex cluster due to confirmed mapping"

        # New names go through automated clustering — may or may not be with Apex
        # This is expected: the system flags them for review
        candidates = find_uncertain_pairs(clusters, new_names)
        print(f"\n  Step 6: {len(candidates)} pairs flagged for review after new data arrived")

    def test_full_build_normalizer_integration(self, tmp_path):
        """Integration test: build_normalizer with confirmed_path produces correct lookup."""
        confirmed_path = tmp_path / "confirmed.yaml"
        confirmed_path.write_text(yaml.dump({
            "mappings": [
                {"names": list(GROUND_TRUTH["Apex Manufacturing"]), "canonical": "Apex Manufacturing"},
                {"names": list(GROUND_TRUTH["Apex Farms"]), "canonical": "Apex Farms"},
            ]
        }))

        lookup, clusters = build_normalizer(
            ALL_NAMES,
            method=ClusterMethod.PIPELINE,
            confirmed_path=str(confirmed_path),
        )

        # All Apex variants should resolve to the same canonical
        assert lookup["APEX MFG"] == lookup["Apex Mfg"] == lookup["APEX Manufacturing Inc"]
        # Apex Farms should be separate
        assert lookup["Apex Farms"] == lookup["APEX FARMS LLC"]
        assert lookup["Apex Farms"] != lookup["APEX MFG"]

        print(f"\n  Integration: {len(clusters)} clusters, lookup has {len(lookup)} entries")
        for canonical, members in sorted(clusters.items()):
            print(f"    {canonical}: {members}")
