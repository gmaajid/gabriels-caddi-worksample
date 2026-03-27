"""Tests for demo data generator."""

import pytest
import pandas as pd
from pathlib import Path
import yaml

from src.ma_registry import MARegistry
from src.demo_generator import generate_demo_data, load_test_scenarios


@pytest.fixture
def registry_with_events(tmp_path):
    reg = MARegistry(path=tmp_path / "ma_registry.yaml")
    apex = reg.add_entity("Apex Manufacturing")
    qf = reg.add_entity("QuickFab Industries")
    reg.add_event("acquisition", "2024-07-15", apex["id"], qf["id"],
                  [{"name": "AQF Holdings", "first_seen": "2024-09-15"}])
    return reg


@pytest.fixture
def scenarios_path(tmp_path):
    scenarios = {
        "metadata": {"generated": "2026-03-27"},
        "scenarios": [
            {"id": "SC-001", "difficulty": 1, "category": "abbreviation",
             "input_name": "APEX MFG", "expected_canonical": "Apex Manufacturing",
             "requires_ma_registry": False},
            {"id": "SC-030", "difficulty": 4, "category": "post_acquisition",
             "input_name": "AQF Holdings", "expected_canonical": "Apex Manufacturing",
             "requires_ma_registry": True},
        ],
    }
    path = tmp_path / "test_scenarios.yaml"
    with open(path, "w") as f:
        yaml.dump(scenarios, f)
    return path


class TestDemoGeneration:
    def test_generates_orders_csv(self, tmp_path, registry_with_events, scenarios_path):
        output_dir = tmp_path / "demo"
        generate_demo_data(
            registry=registry_with_events,
            scenarios_path=scenarios_path,
            output_dir=output_dir,
        )
        assert (output_dir / "demo_orders.csv").exists()
        df = pd.read_csv(output_dir / "demo_orders.csv")
        assert len(df) > 0
        assert "supplier_name" in df.columns
        assert "order_date" in df.columns
        assert "order_id" in df.columns

    def test_orders_use_scenario_names(self, tmp_path, registry_with_events, scenarios_path):
        output_dir = tmp_path / "demo"
        generate_demo_data(
            registry=registry_with_events,
            scenarios_path=scenarios_path,
            output_dir=output_dir,
        )
        df = pd.read_csv(output_dir / "demo_orders.csv")
        names = set(df["supplier_name"])
        assert "APEX MFG" in names
        assert "AQF Holdings" in names

    def test_temporal_consistency(self, tmp_path, registry_with_events, scenarios_path):
        output_dir = tmp_path / "demo"
        generate_demo_data(
            registry=registry_with_events,
            scenarios_path=scenarios_path,
            output_dir=output_dir,
        )
        df = pd.read_csv(output_dir / "demo_orders.csv")
        aqf_rows = df[df["supplier_name"] == "AQF Holdings"]
        for _, row in aqf_rows.iterrows():
            assert row["order_date"] >= "2024-07-15"

    def test_load_scenarios(self, scenarios_path):
        scenarios = load_test_scenarios(scenarios_path)
        assert len(scenarios) == 2
        assert scenarios[0]["id"] == "SC-001"
        assert scenarios[1]["difficulty"] == 4
