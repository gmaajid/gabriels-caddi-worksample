"""Tests for human-in-the-loop review system."""

from pathlib import Path

import yaml

from src.human_review import (
    apply_human_overrides,
    find_uncertain_pairs,
    list_reviews,
    load_confirmed_mappings,
    load_review_decisions,
    write_review_file,
)
from src.supplier_clustering import ClusterMethod, cluster_names


SAMPLE_NAMES = [
    "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
    "AeroFlow Systems", "Precision Thermal Co", "QuickFab Industries",
    "Stellar Metalworks", "TitanForge LLC",
]


def test_find_uncertain_pairs():
    clusters = cluster_names(SAMPLE_NAMES, method=ClusterMethod.HYBRID)
    candidates = find_uncertain_pairs(clusters, SAMPLE_NAMES)
    assert isinstance(candidates, list)
    # Each candidate has required fields
    for c in candidates:
        assert "name_a" in c
        assert "name_b" in c
        assert "tfidf_jaccard" in c
        assert "embedding_cosine" in c
        assert "suggested_action" in c


def test_write_review_file(tmp_path):
    clusters = cluster_names(SAMPLE_NAMES, method=ClusterMethod.HYBRID)
    candidates = find_uncertain_pairs(clusters, SAMPLE_NAMES)
    path = write_review_file(candidates, path=tmp_path / "review.yaml")
    assert path.exists()

    with open(path) as f:
        data = yaml.safe_load(f)
    assert "_instructions" in data
    assert "pairs" in data
    for pair in data["pairs"]:
        assert pair["decision"] == "skip"  # default


def test_load_confirmed_mappings(tmp_path):
    conf_path = tmp_path / "confirmed.yaml"
    conf_path.write_text(yaml.dump({
        "mappings": [
            {"names": ["APEX MFG", "Apex Mfg", "Apex Manufacturing Inc"], "canonical": "Apex Manufacturing"},
            {"names": ["Stellar Metalworks"], "canonical": "Stellar Metalworks"},
        ]
    }))
    lookup = load_confirmed_mappings(conf_path)
    assert lookup["APEX MFG"] == "Apex Manufacturing"
    assert lookup["Apex Mfg"] == "Apex Manufacturing"
    assert lookup["Stellar Metalworks"] == "Stellar Metalworks"


def test_load_confirmed_mappings_missing(tmp_path):
    lookup = load_confirmed_mappings(tmp_path / "nonexistent.yaml")
    assert lookup == {}


def test_load_review_decisions(tmp_path):
    review_path = tmp_path / "review.yaml"
    review_path.write_text(yaml.dump({
        "pairs": [
            {"name_a": "A", "name_b": "B", "decision": "merge"},
            {"name_a": "C", "name_b": "D", "decision": "split"},
            {"name_a": "E", "name_b": "F", "decision": "skip"},
        ]
    }))
    merges, splits = load_review_decisions(review_path)
    assert merges == [("A", "B")]
    assert splits == [("C", "D")]


def test_load_review_decisions_missing(tmp_path):
    merges, splits = load_review_decisions(tmp_path / "nonexistent.yaml")
    assert merges == []
    assert splits == []


def test_apply_human_overrides_confirmed(tmp_path):
    clusters = {
        "APEX Manufacturing Inc": ["APEX MFG", "APEX Manufacturing Inc"],
        "Apex Mfg": ["Apex Manufacturing Inc", "Apex Mfg"],
    }
    conf_path = tmp_path / "confirmed.yaml"
    conf_path.write_text(yaml.dump({
        "mappings": [{
            "names": ["APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc"],
            "canonical": "Apex Manufacturing",
        }]
    }))
    result = apply_human_overrides(clusters, confirmed_path=conf_path, review_path=tmp_path / "nope.yaml")
    # All 4 names should be in one cluster
    assert len(result) == 1
    canonical = list(result.keys())[0]
    assert len(result[canonical]) == 4


def test_apply_human_overrides_merge_decision(tmp_path):
    clusters = {
        "Cluster A": ["Name1", "Name2"],
        "Cluster B": ["Name3"],
    }
    review_path = tmp_path / "review.yaml"
    review_path.write_text(yaml.dump({
        "pairs": [
            {"name_a": "Name1", "name_b": "Name3", "decision": "merge"},
        ]
    }))
    result = apply_human_overrides(clusters, confirmed_path=tmp_path / "nope.yaml", review_path=review_path)
    # Name1, Name2, Name3 should all be in one cluster
    all_members = []
    for members in result.values():
        all_members.extend(members)
    assert set(all_members) == {"Name1", "Name2", "Name3"}
    assert len(result) == 1


def test_apply_human_overrides_split_decision(tmp_path):
    clusters = {
        "Big Cluster": ["Name1", "Name2", "Name3"],
    }
    review_path = tmp_path / "review.yaml"
    review_path.write_text(yaml.dump({
        "pairs": [
            {"name_a": "Name1", "name_b": "Name3", "decision": "split"},
        ]
    }))
    result = apply_human_overrides(clusters, confirmed_path=tmp_path / "nope.yaml", review_path=review_path)
    # Name3 should be split out
    assert len(result) >= 2


def test_apply_no_overrides():
    clusters = {"A": ["A", "B"]}
    result = apply_human_overrides(clusters, confirmed_path=Path("nonexistent"), review_path=Path("nonexistent"))
    assert result == clusters


def test_review_cli_command(tmp_path):
    """Test the CLI review command."""
    from click.testing import CliRunner
    from rag.cli import cli

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "orders.csv").write_text(
        "order_id,supplier_name,unit_price\n"
        "PO-001,APEX MFG,100\n"
        "PO-002,Apex Manufacturing Inc,200\n"
        "PO-003,AeroFlow Systems,300\n"
    )

    runner = CliRunner()
    result = runner.invoke(cli, [
        "review",
        "--data-dir", str(data_dir),
    ])
    assert result.exit_code == 0
    assert "name occurrences" in result.output


def test_reviews_cli_command():
    """Test the CLI reviews listing command."""
    from click.testing import CliRunner
    from rag.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["reviews"])
    assert result.exit_code == 0


def test_list_reviews():
    reviews = list_reviews()
    assert isinstance(reviews, list)
    for r in reviews:
        assert "review_id" in r
        assert "status" in r
        assert "total" in r
        assert "pending" in r
