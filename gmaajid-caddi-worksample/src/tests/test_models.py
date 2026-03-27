"""Tests for Pydantic models and supplier normalization."""

import pytest

from src.models import (
    QualityInspection,
    RFQResponse,
    RejectionSeverity,
    SupplierOrder,
    init_supplier_normalizer,
    normalize_supplier,
    get_supplier_clusters,
)
from src.supplier_clustering import (
    build_normalizer,
    cluster_supplier_names,
    jaccard_similarity,
    tokenize_company,
)


# --- All raw names from the actual dataset ---
ALL_RAW_NAMES = [
    "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
    "AeroFlow Systems", "Precision Thermal Co", "QuickFab Industries",
    "Stellar Metalworks", "TitanForge LLC",
]


@pytest.fixture(autouse=True)
def _init_normalizer():
    """Initialize the cluster-based normalizer before each test."""
    init_supplier_normalizer(ALL_RAW_NAMES)


# --- Tokenization ---

def test_tokenize_expands_abbreviations():
    assert tokenize_company("APEX MFG") == {"apex", "manufacturing"}
    assert tokenize_company("Apex Mfg") == {"apex", "manufacturing"}


def test_tokenize_strips_legal_suffixes():
    assert tokenize_company("Apex Manufacturing Inc") == {"apex", "manufacturing"}
    assert tokenize_company("TitanForge LLC") == {"titan", "forge"}
    assert "precision" in tokenize_company("Precision Thermal Co")
    assert "thermal" in tokenize_company("Precision Thermal Co")


def test_tokenize_negative_cases():
    assert tokenize_company("APEX Farms") == {"apex", "farms"}
    assert tokenize_company("Apex Logistics Inc") == {"apex", "logistics"}


# --- Jaccard Similarity ---

def test_jaccard_identical():
    assert jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint():
    assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_partial():
    assert abs(jaccard_similarity({"a", "b"}, {"a", "c"}) - 1 / 3) < 1e-9


# --- Clustering ---

def test_cluster_apex_variants():
    clusters = cluster_supplier_names(ALL_RAW_NAMES, threshold=0.5)
    apex_cluster = None
    for canonical, members in clusters.items():
        if "APEX MFG" in members:
            apex_cluster = members
            break
    assert apex_cluster is not None
    assert set(apex_cluster) == {
        "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc"
    }


def test_cluster_each_supplier_separate():
    """All 6 canonical suppliers should form separate clusters."""
    clusters = cluster_supplier_names(ALL_RAW_NAMES, threshold=0.5)
    assert len(clusters) == 6


# --- Model Performance: Precision / Recall / F1 ---

def _evaluate_clustering(
    ground_truth: dict[str, list[str]],
    threshold: float = 0.5,
) -> dict[str, float]:
    """Evaluate clustering against ground-truth groups.

    Uses pairwise evaluation:
    - True positive:  two names in same expected group AND same predicted cluster
    - False positive: two names in DIFFERENT expected groups but same predicted cluster
    - False negative: two names in same expected group but DIFFERENT predicted clusters

    Returns dict with precision, recall, f1.
    """
    all_names = []
    name_to_group: dict[str, str] = {}
    for group_label, variants in ground_truth.items():
        all_names.extend(variants)
        for v in variants:
            name_to_group[v] = group_label

    clusters = cluster_supplier_names(all_names, threshold=threshold)
    name_to_cluster: dict[str, str] = {}
    for canonical, members in clusters.items():
        for m in members:
            name_to_cluster[m] = canonical

    tp = fp = fn = 0
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

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def test_model_performance_real_data():
    """Evaluate clustering on the actual Hoth Industries dataset (ground truth known)."""
    ground_truth = {
        "Apex Manufacturing": [
            "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
        ],
        "AeroFlow Systems": ["AeroFlow Systems"],
        "Precision Thermal Co": ["Precision Thermal Co"],
        "QuickFab Industries": ["QuickFab Industries"],
        "Stellar Metalworks": ["Stellar Metalworks"],
        "TitanForge LLC": ["TitanForge LLC"],
    }
    metrics = _evaluate_clustering(ground_truth)
    print(f"\n  Real data: P={metrics['precision']:.2%} R={metrics['recall']:.2%} F1={metrics['f1']:.2%}")
    print(f"  TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']}")
    assert metrics["precision"] == 1.0, f"Precision {metrics['precision']:.2%} (expected 100%)"
    assert metrics["recall"] == 1.0, f"Recall {metrics['recall']:.2%} (expected 100%)"


def test_model_performance_with_confusable_negatives():
    """Names that share a token (e.g. 'Apex') but are different companies must NOT merge."""
    ground_truth = {
        "Apex Manufacturing": [
            "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
        ],
        "Apex Farms": ["APEX Farms", "Apex Farms LLC"],
        "Apex Logistics": ["Apex Logistics", "APEX LOGISTICS INC"],
        "AeroFlow Systems": ["AeroFlow Systems"],
        "Stellar Metalworks": ["Stellar Metalworks"],
        "Stellar Dynamics": ["Stellar Dynamics Inc", "STELLAR DYNAMICS"],
    }
    metrics = _evaluate_clustering(ground_truth)
    print(f"\n  With confusables: P={metrics['precision']:.2%} R={metrics['recall']:.2%} F1={metrics['f1']:.2%}")
    print(f"  TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']}")
    assert metrics["precision"] >= 0.95, f"Precision {metrics['precision']:.2%} below 95%"
    assert metrics["recall"] >= 0.95, f"Recall {metrics['recall']:.2%} below 95%"


def test_model_performance_abbreviation_variants():
    """Test that abbreviation expansion correctly links variants."""
    ground_truth = {
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
    metrics = _evaluate_clustering(ground_truth)
    print(f"\n  Abbreviations: P={metrics['precision']:.2%} R={metrics['recall']:.2%} F1={metrics['f1']:.2%}")
    print(f"  TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']}")
    assert metrics["precision"] >= 0.90, f"Precision {metrics['precision']:.2%} below 90%"
    assert metrics["recall"] >= 0.90, f"Recall {metrics['recall']:.2%} below 90%"


def test_model_performance_single_token_companies():
    """Compound names like TitanForge should not merge with TitanSteel.

    CamelCase splitting means 'TitanForge' -> {titan, forge} and
    'TitanSteel' -> {titan, steel}, Jaccard=1/3=0.33 < threshold.
    All-caps variants (TITANFORGE) lack CamelCase boundaries, so the
    embedding component handles them.
    """
    ground_truth = {
        "TitanForge": ["TitanForge", "TitanForge LLC", "TITANFORGE"],
        "TitanSteel": ["TitanSteel", "TitanSteel Inc", "TITANSTEEL LLC"],
        "QuickFab": ["QuickFab Industries", "QUICKFAB INDUSTRIES", "quickfab ind"],
    }
    metrics = _evaluate_clustering(ground_truth)
    print(f"\n  Single-token: P={metrics['precision']:.2%} R={metrics['recall']:.2%} F1={metrics['f1']:.2%}")
    print(f"  TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']}")
    # Precision must be high (don't merge different companies)
    assert metrics["precision"] >= 0.90, f"Precision {metrics['precision']:.2%} below 90%"
    # Recall may be lower due to all-caps compound word limitation
    assert metrics["recall"] >= 0.30, f"Recall {metrics['recall']:.2%} below 30%"


def test_model_performance_threshold_sensitivity():
    """Evaluate F1 at different thresholds to find the sweet spot."""
    ground_truth = {
        "Apex Manufacturing": [
            "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
        ],
        "Apex Farms": ["APEX Farms", "Apex Farms LLC"],
        "Stellar Metalworks": ["Stellar Metalworks", "Stellar Metalworks Inc"],
        "Stellar Dynamics": ["Stellar Dynamics", "STELLAR DYNAMICS"],
        "QuickFab Industries": ["QuickFab Industries", "QUICKFAB IND"],
        "AeroFlow Systems": ["AeroFlow Systems", "Aero Flow Sys Inc"],
    }
    results = []
    for threshold in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        metrics = _evaluate_clustering(ground_truth, threshold=threshold)
        results.append((threshold, metrics))

    print("\n  Threshold sensitivity:")
    print(f"  {'Threshold':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    best_f1 = 0
    best_threshold = 0.5
    for threshold, metrics in results:
        print(f"  {threshold:>10.1f} {metrics['precision']:>10.2%} {metrics['recall']:>10.2%} {metrics['f1']:>10.2%}")
        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            best_threshold = threshold

    print(f"  Best threshold: {best_threshold} (F1={best_f1:.2%})")
    # The default threshold of 0.5 should be in the top tier
    default_metrics = next(m for t, m in results if t == 0.5)
    assert default_metrics["f1"] >= 0.85, f"Default threshold F1={default_metrics['f1']:.2%} below 85%"


# --- Normalizer Integration ---

def test_normalize_apex_variants():
    canonical = normalize_supplier("APEX MFG")
    assert canonical == normalize_supplier("Apex Mfg")
    assert canonical == normalize_supplier("APEX Manufacturing Inc")
    assert canonical == normalize_supplier("Apex Manufacturing Inc")


def test_normalize_all_suppliers_resolve():
    canonical_names = set()
    for name in ALL_RAW_NAMES:
        canonical_names.add(normalize_supplier(name))
    assert len(canonical_names) == 6


def test_normalize_passthrough_unknown():
    assert normalize_supplier("Unknown Supplier") == "Unknown Supplier"


def test_get_clusters_structure():
    clusters = get_supplier_clusters()
    assert isinstance(clusters, dict)
    assert len(clusters) == 6
    for canonical, variants in clusters.items():
        assert canonical in variants


# --- Pydantic Model Tests ---

def test_supplier_order_computed_fields():
    order = SupplierOrder(
        order_id="PO-2021-011",
        supplier_name_raw="APEX MFG",
        part_number="CTRL-9998",
        part_description="Touch Screen Controller",
        order_date="2021-10-01",
        promised_date="2021-11-12",
        actual_delivery_date="2021-11-15",
        quantity=10,
        unit_price=100.0,
        po_amount=1000.0,
    )
    assert order.days_late == 3
    assert order.is_late is True


def test_supplier_order_on_time():
    order = SupplierOrder(
        order_id="PO-2021-011",
        supplier_name_raw="Apex Mfg",
        part_number="X",
        part_description="X",
        order_date="2021-10-01",
        promised_date="2021-11-12",
        actual_delivery_date="2021-11-10",
        quantity=1,
        unit_price=1.0,
        po_amount=1.0,
    )
    assert order.days_late == 0
    assert order.is_late is False


def test_supplier_order_missing_delivery():
    order = SupplierOrder(
        order_id="PO-2025-501",
        supplier_name_raw="Stellar Metalworks",
        part_number="X",
        part_description="X",
        order_date="2021-10-01",
        promised_date="2025-10-15",
        actual_delivery_date=None,
        quantity=1,
        unit_price=1.0,
        po_amount=1.0,
    )
    assert order.days_late is None
    assert order.is_late is None


def test_quality_inspection_rejection_rate():
    insp = QualityInspection(
        inspection_id="INS-001",
        order_id="PO-2021-011",
        inspection_date="2021-11-18",
        parts_inspected=100,
        parts_rejected=5,
        rejection_reason="Burrs on edges",
        rework_required=True,
    )
    assert abs(insp.rejection_rate - 0.05) < 1e-9
    assert insp.severity == RejectionSeverity.MACHINING


def test_quality_inspection_structural_severity():
    insp = QualityInspection(
        inspection_id="INS-002",
        order_id="PO-2021-011",
        inspection_date="2021-11-18",
        parts_inspected=100,
        parts_rejected=20,
        rejection_reason="Welding defects multiple tubes",
        rework_required=True,
    )
    assert insp.severity == RejectionSeverity.STRUCTURAL


def test_rfq_response_normalization():
    rfq = RFQResponse(
        rfq_id="RFQ-2021-001",
        supplier_name_raw="APEX MFG",
        part_description="Vibration Mount",
        quote_date="2022-02-10",
        quoted_price=27.4,
        lead_time_weeks=5,
        notes="Industrial grade",
    )
    assert rfq.supplier_name == normalize_supplier("Apex Manufacturing Inc")
