"""Tests for benchmarking: precision/recall calculation by difficulty tier."""

import pytest
from src.benchmark import compute_metrics, BenchmarkResult


class TestMetrics:
    def test_perfect_score(self):
        results = [
            BenchmarkResult("APEX MFG", "Apex Manufacturing", "Apex Manufacturing", True, 1),
            BenchmarkResult("Apex Mfg", "Apex Manufacturing", "Apex Manufacturing", True, 1),
        ]
        metrics = compute_metrics(results)
        assert metrics["overall"]["precision"] == 1.0
        assert metrics["overall"]["recall"] == 1.0
        assert metrics["overall"]["f1"] == 1.0

    def test_partial_recall(self):
        results = [
            BenchmarkResult("APEX MFG", "Apex Manufacturing", "Apex Manufacturing", True, 1),
            BenchmarkResult("AQF Holdings", "Apex Manufacturing", None, False, 4),
        ]
        metrics = compute_metrics(results)
        assert metrics["overall"]["recall"] == 0.5
        assert metrics["overall"]["precision"] == 1.0

    def test_wrong_resolution(self):
        results = [
            BenchmarkResult("APEX MFG", "Apex Manufacturing", "QuickFab Industries", True, 1),
        ]
        metrics = compute_metrics(results)
        assert metrics["overall"]["precision"] == 0.0

    def test_metrics_by_tier(self):
        results = [
            BenchmarkResult("A", "X", "X", True, 1),
            BenchmarkResult("B", "X", "X", True, 1),
            BenchmarkResult("C", "Y", None, False, 4),
        ]
        metrics = compute_metrics(results)
        assert metrics["by_tier"][1]["recall"] == 1.0
        assert metrics["by_tier"][4]["recall"] == 0.0

    def test_empty_results(self):
        metrics = compute_metrics([])
        assert metrics["overall"]["precision"] == 0.0
        assert metrics["overall"]["recall"] == 0.0
