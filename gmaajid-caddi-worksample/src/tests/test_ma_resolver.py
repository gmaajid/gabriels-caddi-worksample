"""Tests for M&A chain resolver — date-aware name resolution."""

import pytest
from src.ma_registry import MARegistry
from src.ma_resolver import MAResolver, ResolutionResult


@pytest.fixture
def registry_with_events(tmp_path):
    """Registry with 4 M&A events matching the spec."""
    reg = MARegistry(path=tmp_path / "ma_registry.yaml")
    apex = reg.add_entity("Apex Manufacturing", friendly="apex-mfg")
    qf = reg.add_entity("QuickFab Industries", friendly="quickfab")
    pt = reg.add_entity("Precision Thermal Co", friendly="precision-thermal")
    sm = reg.add_entity("Stellar Metalworks", friendly="stellar")
    tf = reg.add_entity("TitanForge LLC", friendly="titanforge")
    af = reg.add_entity("AeroFlow Systems", friendly="aeroflow")

    # MA-1: Apex acquires QuickFab
    reg.add_event("acquisition", "2024-07-15", apex["id"], qf["id"],
                  [{"name": "Apex-QuickFab Industries", "first_seen": "2024-08-01"},
                   {"name": "AQF Holdings", "first_seen": "2024-09-15"}])

    # MA-2: Precision Thermal rebrands
    reg.add_event("rebrand", "2025-01-01", pt["id"], pt["id"],
                  [{"name": "Zenith Thermal Solutions", "first_seen": "2025-01-15"},
                   {"name": "Zenith Thermal", "first_seen": "2025-02-01"}])

    # MA-3: Stellar + TitanForge merge
    reg.add_event("merger", "2023-06-01", sm["id"], tf["id"],
                  [{"name": "StellarForge Industries", "first_seen": "2023-07-01"}],
                  co_merged=[sm["id"], tf["id"]])

    # MA-4: AeroFlow restructures
    reg.add_event("restructure", "2024-01-15", af["id"], af["id"],
                  [{"name": "AeroFlow Technologies", "first_seen": "2024-02-01"}])

    return reg


@pytest.fixture
def resolver(registry_with_events):
    return MAResolver(registry_with_events)


class TestDirectResolution:
    def test_resulting_name_resolves(self, resolver):
        result = resolver.resolve("AQF Holdings", "2024-10-01")
        assert result.resolved
        assert result.canonical == "Apex Manufacturing"
        assert result.source == "ma_registry"

    def test_resulting_name_with_date_before_event_unresolved(self, resolver):
        result = resolver.resolve("AQF Holdings", "2024-06-01")
        assert not result.resolved

    def test_rebrand_resolves(self, resolver):
        result = resolver.resolve("Zenith Thermal Solutions", "2025-03-01")
        assert result.resolved
        assert result.canonical == "Precision Thermal Co"

    def test_merger_resolves_to_acquirer(self, resolver):
        result = resolver.resolve("StellarForge Industries", "2023-08-01")
        assert result.resolved
        assert result.canonical == "Stellar Metalworks"

    def test_restructure_resolves(self, resolver):
        result = resolver.resolve("AeroFlow Technologies", "2024-03-01")
        assert result.resolved
        assert result.canonical == "AeroFlow Systems"


class TestEdgeCases:
    def test_unknown_name_unresolved(self, resolver):
        result = resolver.resolve("Totally Unknown Corp", "2024-01-01")
        assert not result.resolved

    def test_exact_event_date_resolves(self, resolver):
        result = resolver.resolve("AQF Holdings", "2024-07-15")
        assert result.resolved

    def test_resolution_result_has_event_id(self, resolver):
        result = resolver.resolve("AQF Holdings", "2024-10-01")
        assert result.event_id is not None

    def test_resolution_result_has_chain(self, resolver):
        result = resolver.resolve("AQF Holdings", "2024-10-01")
        assert len(result.chain) >= 1
