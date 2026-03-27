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
