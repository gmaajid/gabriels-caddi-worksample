"""Tests for anchor-based word voting resolver."""

import pytest
from src.anchor_resolver import AnchorResolver, AnchorResult


@pytest.fixture
def resolver():
    """Resolver with the 6 Hoth canonical names as anchors."""
    canonicals = [
        "Apex Manufacturing",
        "QuickFab Industries",
        "Precision Thermal Co",
        "Stellar Metalworks",
        "TitanForge LLC",
        "AeroFlow Systems",
    ]
    return AnchorResolver(canonicals)


class TestClearMatches:
    def test_exact_match(self, resolver):
        r = resolver.resolve("Apex Manufacturing")
        assert r.canonical == "Apex Manufacturing"
        assert r.confidence >= 0.9

    def test_abbreviation(self, resolver):
        r = resolver.resolve("APEX MFG")
        assert r.canonical == "Apex Manufacturing"
        assert r.confidence >= 0.8

    def test_case_variation(self, resolver):
        r = resolver.resolve("apex manufacturing inc")
        assert r.canonical == "Apex Manufacturing"

    def test_legal_suffix_missing(self, resolver):
        r = resolver.resolve("TitanForge")
        assert r.canonical == "TitanForge LLC"

    def test_abbreviation_sys(self, resolver):
        r = resolver.resolve("AEROFLOW SYS")
        assert r.canonical == "AeroFlow Systems"

    def test_co_expanded(self, resolver):
        r = resolver.resolve("Precision Thermal Company")
        assert r.canonical == "Precision Thermal Co"

    def test_all_caps(self, resolver):
        r = resolver.resolve("STELLAR METALWORKS")
        assert r.canonical == "Stellar Metalworks"

    def test_lowercase(self, resolver):
        r = resolver.resolve("quickfab industries")
        assert r.canonical == "QuickFab Industries"


class TestTypos:
    def test_missing_letter(self, resolver):
        r = resolver.resolve("Stellr Metalworks")
        assert r.canonical == "Stellar Metalworks"

    def test_extra_space_compound(self, resolver):
        r = resolver.resolve("Titan Forge LLC")
        assert r.canonical == "TitanForge LLC"

    def test_doubled_letter(self, resolver):
        r = resolver.resolve("Apexx Manufacturing")
        assert r.canonical == "Apex Manufacturing"


class TestSplitVotes:
    def test_acquisition_compound_name(self, resolver):
        """Name containing tokens from two different canonicals."""
        r = resolver.resolve("Apex-QuickFab Industries")
        assert r.split_vote
        assert len(r.voted_canonicals) >= 2
        # Should have votes for both Apex and QuickFab
        voted_names = {vc["canonical"] for vc in r.voted_canonicals}
        assert "Apex Manufacturing" in voted_names
        assert "QuickFab Industries" in voted_names

    def test_merger_compound_name(self, resolver):
        r = resolver.resolve("StellarForge Industries")
        # "stellar" votes for Stellar Metalworks, "forge" for TitanForge
        assert r.split_vote or r.confidence < 0.8


class TestNoMatch:
    def test_unknown_company(self, resolver):
        r = resolver.resolve("Pacific Northwest Fabricators")
        assert r.canonical is None or r.confidence < 0.3

    def test_zero_overlap_rebrand(self, resolver):
        """Zenith Thermal has zero token overlap with any canonical."""
        r = resolver.resolve("Zenith Thermal Solutions")
        assert r.canonical is None or r.confidence < 0.3

    def test_similar_but_different(self, resolver):
        """AeroTech is NOT AeroFlow."""
        r = resolver.resolve("AeroTech Systems")
        # Should either not match, or match with low confidence
        if r.canonical == "AeroFlow Systems":
            assert r.confidence < 0.5


class TestFalsePositiveTraps:
    def test_apex_farms_not_apex_manufacturing(self, resolver):
        """Apex Farms should NOT resolve to Apex Manufacturing."""
        r = resolver.resolve("Apex Farms LLC")
        assert r.canonical != "Apex Manufacturing"

    def test_summit_manufacturing_not_apex(self, resolver):
        r = resolver.resolve("Summit Manufacturing LLC")
        assert r.canonical != "Apex Manufacturing" or r.confidence < 0.4
