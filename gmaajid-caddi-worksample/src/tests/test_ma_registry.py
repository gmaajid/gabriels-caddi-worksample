"""Tests for M&A registry entity and event management."""
import pytest
from pathlib import Path
from src.ma_registry import MARegistry

@pytest.fixture
def tmp_registry(tmp_path):
    path = tmp_path / "ma_registry.yaml"
    return MARegistry(path=path)

class TestEntityCRUD:
    def test_add_entity_generates_id(self, tmp_registry):
        entity = tmp_registry.add_entity("Apex Manufacturing")
        assert len(entity["id"]) == 6
        assert entity["name"] == "Apex Manufacturing"
        assert entity["friendly"] == "apex-manufacturing"

    def test_add_entity_custom_friendly(self, tmp_registry):
        entity = tmp_registry.add_entity("Apex Manufacturing", friendly="apex-mfg")
        assert entity["friendly"] == "apex-mfg"

    def test_add_entity_persists(self, tmp_registry):
        tmp_registry.add_entity("Apex Manufacturing")
        tmp_registry.save()
        reloaded = MARegistry(path=tmp_registry.path)
        assert len(reloaded.entities) == 1
        assert reloaded.entities[0]["name"] == "Apex Manufacturing"

    def test_get_entity_by_id(self, tmp_registry):
        entity = tmp_registry.add_entity("Apex Manufacturing")
        found = tmp_registry.get_entity(entity["id"])
        assert found["name"] == "Apex Manufacturing"

    def test_get_entity_by_friendly(self, tmp_registry):
        tmp_registry.add_entity("Apex Manufacturing", friendly="apex-mfg")
        found = tmp_registry.get_entity("apex-mfg")
        assert found["name"] == "Apex Manufacturing"

    def test_get_entity_not_found(self, tmp_registry):
        assert tmp_registry.get_entity("nonexistent") is None

    def test_remove_entity(self, tmp_registry):
        entity = tmp_registry.add_entity("Apex Manufacturing")
        tmp_registry.remove_entity(entity["id"])
        assert tmp_registry.get_entity(entity["id"]) is None

    def test_unique_ids(self, tmp_registry):
        e1 = tmp_registry.add_entity("Apex Manufacturing")
        e2 = tmp_registry.add_entity("QuickFab Industries")
        assert e1["id"] != e2["id"]

    def test_friendly_name_generation(self, tmp_registry):
        e = tmp_registry.add_entity("Knight Fastener Fabrication Services")
        assert e["friendly"] == "knight-fastener-fabrication-services"

class TestDivisions:
    def test_add_division(self, tmp_registry):
        parent = tmp_registry.add_entity("Apex Manufacturing")
        div = tmp_registry.add_division(parent["id"], "Bright Star Foundrys")
        assert div["parent"] == parent["id"]
        assert div["name"] == "Bright Star Foundrys"
        parent = tmp_registry.get_entity(parent["id"])
        assert f"{parent['id']}:{div['id']}" in parent.get("divisions", [])

    def test_get_division_by_composite_key(self, tmp_registry):
        parent = tmp_registry.add_entity("Apex Manufacturing")
        div = tmp_registry.add_division(parent["id"], "Bright Star Foundrys")
        composite = f"{parent['id']}:{div['id']}"
        found = tmp_registry.get_entity(composite)
        assert found["name"] == "Bright Star Foundrys"

    def test_get_division_by_friendly_pair(self, tmp_registry):
        parent = tmp_registry.add_entity("Apex Manufacturing", friendly="apex-mfg")
        div = tmp_registry.add_division(parent["id"], "Bright Star Foundrys", friendly="bright-star")
        found = tmp_registry.get_entity("apex-mfg:bright-star")
        assert found["name"] == "Bright Star Foundrys"

    def test_division_not_merged_with_parent(self, tmp_registry):
        parent = tmp_registry.add_entity("Apex Manufacturing")
        div = tmp_registry.add_division(parent["id"], "Bright Star Foundrys")
        assert div["id"] != parent["id"]

    def test_remove_division_updates_parent(self, tmp_registry):
        parent = tmp_registry.add_entity("Apex Manufacturing")
        div = tmp_registry.add_division(parent["id"], "Bright Star Foundrys")
        composite = f"{parent['id']}:{div['id']}"
        tmp_registry.remove_entity(div["id"])
        parent = tmp_registry.get_entity(parent["id"])
        assert composite not in parent.get("divisions", [])


class TestEventCRUD:
    def test_add_event(self, tmp_registry):
        apex = tmp_registry.add_entity("Apex Manufacturing")
        qf = tmp_registry.add_entity("QuickFab Industries")
        event = tmp_registry.add_event(
            event_type="acquisition",
            date="2024-07-15",
            acquirer_id=apex["id"],
            acquired_id=qf["id"],
            resulting_names=[
                {"name": "Apex-QuickFab Industries", "first_seen": "2024-08-01"},
                {"name": "AQF Holdings", "first_seen": "2024-09-15"},
            ],
            notes="QuickFab absorbed into Apex",
        )
        assert event["id"].startswith("ma-")
        assert event["type"] == "acquisition"
        assert event["acquirer"] == apex["id"]
        assert event["acquired"] == qf["id"]
        assert len(event["resulting_names"]) == 2

    def test_add_merger_with_co_merged(self, tmp_registry):
        s = tmp_registry.add_entity("Stellar Metalworks")
        t = tmp_registry.add_entity("TitanForge LLC")
        event = tmp_registry.add_event(
            event_type="merger",
            date="2023-06-01",
            acquirer_id=s["id"],
            acquired_id=t["id"],
            co_merged=[s["id"], t["id"]],
            resulting_names=[{"name": "StellarForge Industries"}],
        )
        assert event["co_merged"] == [s["id"], t["id"]]

    def test_add_rebrand_same_entity(self, tmp_registry):
        pt = tmp_registry.add_entity("Precision Thermal Co")
        event = tmp_registry.add_event(
            event_type="rebrand",
            date="2025-01-01",
            acquirer_id=pt["id"],
            acquired_id=pt["id"],
            resulting_names=[{"name": "Zenith Thermal Solutions"}],
        )
        assert event["acquirer"] == event["acquired"]

    def test_get_event(self, tmp_registry):
        apex = tmp_registry.add_entity("Apex Manufacturing")
        qf = tmp_registry.add_entity("QuickFab Industries")
        event = tmp_registry.add_event(
            event_type="acquisition",
            date="2024-07-15",
            acquirer_id=apex["id"],
            acquired_id=qf["id"],
            resulting_names=[{"name": "AQF Holdings"}],
        )
        found = tmp_registry.get_event(event["id"])
        assert found["type"] == "acquisition"

    def test_remove_event(self, tmp_registry):
        apex = tmp_registry.add_entity("Apex Manufacturing")
        qf = tmp_registry.add_entity("QuickFab Industries")
        event = tmp_registry.add_event(
            event_type="acquisition",
            date="2024-07-15",
            acquirer_id=apex["id"],
            acquired_id=qf["id"],
            resulting_names=[{"name": "AQF Holdings"}],
        )
        tmp_registry.remove_event(event["id"])
        assert tmp_registry.get_event(event["id"]) is None

    def test_event_validates_entity_ids(self, tmp_registry):
        apex = tmp_registry.add_entity("Apex Manufacturing")
        with pytest.raises(ValueError, match="not found"):
            tmp_registry.add_event(
                event_type="acquisition",
                date="2024-07-15",
                acquirer_id=apex["id"],
                acquired_id="nonexistent",
                resulting_names=[{"name": "AQF Holdings"}],
            )

    def test_list_events(self, tmp_registry):
        apex = tmp_registry.add_entity("Apex Manufacturing")
        qf = tmp_registry.add_entity("QuickFab Industries")
        tmp_registry.add_event(
            event_type="acquisition",
            date="2024-07-15",
            acquirer_id=apex["id"],
            acquired_id=qf["id"],
            resulting_names=[{"name": "AQF Holdings"}],
        )
        assert len(tmp_registry.list_events()) == 1

    def test_event_persists(self, tmp_registry):
        apex = tmp_registry.add_entity("Apex Manufacturing")
        qf = tmp_registry.add_entity("QuickFab Industries")
        tmp_registry.add_event(
            event_type="acquisition",
            date="2024-07-15",
            acquirer_id=apex["id"],
            acquired_id=qf["id"],
            resulting_names=[{"name": "AQF Holdings"}],
        )
        reloaded = MARegistry(path=tmp_registry.path)
        assert len(reloaded.events) == 1
        assert reloaded.events[0]["type"] == "acquisition"
