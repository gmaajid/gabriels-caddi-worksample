"""Tests for M&A chain validation: cycles, broken chains, temporal conflicts,
ambiguous forks, and orphaned entities."""

import pytest
from src.ma_registry import MARegistry
from src.chain_validator import validate_registry, AlertType


@pytest.fixture
def registry(tmp_path):
    return MARegistry(path=tmp_path / "ma_registry.yaml")


class TestCycleDetection:
    def test_no_cycle(self, registry):
        a = registry.add_entity("Company A")
        b = registry.add_entity("Company B")
        registry.add_event("acquisition", "2024-01-01", a["id"], b["id"],
                          [{"name": "AB Corp"}])
        alerts = validate_registry(registry)
        assert not any(a["type"] == AlertType.CYCLE for a in alerts)

    def test_cycle_detected(self, registry):
        a = registry.add_entity("Company A")
        b = registry.add_entity("Company B")
        registry.add_event("acquisition", "2024-01-01", a["id"], b["id"],
                          [{"name": "AB Corp"}])
        registry.add_event("acquisition", "2024-06-01", b["id"], a["id"],
                          [{"name": "BA Corp"}])
        alerts = validate_registry(registry)
        cycle_alerts = [a for a in alerts if a["type"] == AlertType.CYCLE]
        assert len(cycle_alerts) >= 1
        assert "cycle" in cycle_alerts[0]["message"].lower()


class TestTemporalConflict:
    def test_no_conflict(self, registry):
        a = registry.add_entity("Company A")
        b = registry.add_entity("Company B")
        registry.add_event("acquisition", "2024-01-01", a["id"], b["id"],
                          [{"name": "AB Corp", "first_seen": "2024-02-01"}])
        alerts = validate_registry(registry)
        assert not any(a["type"] == AlertType.TEMPORAL_CONFLICT for a in alerts)

    def test_first_seen_before_event_date(self, registry):
        a = registry.add_entity("Company A")
        b = registry.add_entity("Company B")
        registry.add_event("acquisition", "2024-06-01", a["id"], b["id"],
                          [{"name": "AB Corp", "first_seen": "2024-01-01"}])
        alerts = validate_registry(registry)
        temporal = [a for a in alerts if a["type"] == AlertType.TEMPORAL_CONFLICT]
        assert len(temporal) >= 1


class TestOrphanedEntity:
    def test_entity_in_event_is_not_orphaned(self, registry):
        a = registry.add_entity("Company A")
        b = registry.add_entity("Company B")
        registry.add_event("acquisition", "2024-01-01", a["id"], b["id"],
                          [{"name": "AB Corp"}])
        alerts = validate_registry(registry)
        orphans = [a for a in alerts if a["type"] == AlertType.ORPHANED_ENTITY]
        assert not orphans

    def test_entity_in_no_event_is_orphaned(self, registry):
        registry.add_entity("Company A")
        registry.add_entity("Company B")
        alerts = validate_registry(registry, check_orphans_against_data=False)
        orphans = [a for a in alerts if a["type"] == AlertType.ORPHANED_ENTITY]
        assert len(orphans) >= 1


class TestValidChain:
    def test_valid_registry_no_alerts(self, registry):
        a = registry.add_entity("Apex Manufacturing")
        b = registry.add_entity("QuickFab Industries")
        registry.add_event("acquisition", "2024-07-15", a["id"], b["id"],
                          [{"name": "AQF Holdings", "first_seen": "2024-08-01"}])
        alerts = validate_registry(registry, check_orphans_against_data=False)
        errors = [a for a in alerts if a["severity"] == "error"]
        assert not errors
