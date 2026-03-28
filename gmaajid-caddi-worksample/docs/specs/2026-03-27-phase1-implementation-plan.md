# Phase 1: AI-Assisted Procurement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an M&A-aware entity resolution system that automatically resolves supplier names across corporate events, generates demo data with difficulty tiers, benchmarks precision/recall, and visualizes the relationship graph in a browser.

**Architecture:** Three-stage pipeline: (1) existing clustering for abbreviations/typos, (2) M&A registry chain traversal for acquisitions/rebrands, (3) validation + human escalation for broken chains. Entity IDs (short hashes + friendly names) replace text keys throughout. Web visualization uses D3.js force-directed graph. Everything runs from a single Docker image.

**Tech Stack:** Python 3.12, Click (CLI), PyYAML, sentence-transformers, ChromaDB, D3.js (visualization), pytest, Docker

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/ma_registry.py` | Entity + M&A event CRUD, YAML persistence, ID generation |
| `src/ma_resolver.py` | Stage 2 resolver: date-aware chain traversal |
| `src/chain_validator.py` | Detect broken chains, cycles, temporal conflicts, ambiguous forks, orphans |
| `src/demo_generator.py` | Generate synthetic CSVs from M&A registry + test scenarios |
| `src/benchmark.py` | Run resolution pipeline against ground truth, compute metrics by tier |
| `src/tests/test_ma_registry.py` | Tests for entity/event CRUD, ID generation, divisions |
| `src/tests/test_ma_resolver.py` | Tests for chain traversal, date filtering, multi-hop |
| `src/tests/test_chain_validator.py` | Tests for each error condition |
| `src/tests/test_demo_generator.py` | Tests for CSV generation, name corruption |
| `src/tests/test_benchmark.py` | Tests for metric calculation |
| `config/ma_registry.yaml` | Pre-built M&A registry for demo |
| `config/test_scenarios.yaml` | Ground truth test cases with difficulty tiers |
| `web/index.html` | Single-page visualization app |
| `web/graph.js` | D3.js force-directed graph rendering |
| `web/style.css` | Graph styling |

### Modified Files

| File | Changes |
|------|---------|
| `rag/cli.py` | Add `ma` subcommand group, `demo` subcommand group, `viz` command |
| `rag/config.py` | Add `MA_REGISTRY_PATH`, `TEST_SCENARIOS_PATH`, `DEMO_DIR`, `WEB_DIR` |
| `Dockerfile` | Update for web server, pre-download model |
| `pyproject.toml` | No new dependencies needed (D3.js is client-side) |

---

## Task 1: Config Paths

**Files:**
- Modify: `rag/config.py`

- [ ] **Step 1: Add new path constants**

```python
# Add to rag/config.py after existing path definitions:

MA_REGISTRY_PATH = CONFIG_DIR / "ma_registry.yaml"
TEST_SCENARIOS_PATH = CONFIG_DIR / "test_scenarios.yaml"
DEMO_DIR = DATA_DIR / "demo"
WEB_DIR = PROJECT_ROOT / "web"
```

- [ ] **Step 2: Verify imports still work**

Run: `cd /home/gmaajid/projects/gmaajid-caddi-worksample && .venv/bin/python -c "from rag.config import MA_REGISTRY_PATH, TEST_SCENARIOS_PATH, DEMO_DIR, WEB_DIR; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add rag/config.py
git commit -m "config: add paths for M&A registry, test scenarios, demo data, web"
```

---

## Task 2: M&A Registry — Entity Model

**Files:**
- Create: `src/ma_registry.py`
- Create: `src/tests/test_ma_registry.py`

- [ ] **Step 1: Write failing tests for entity CRUD**

Create `src/tests/test_ma_registry.py`:

```python
"""Tests for M&A registry entity and event management."""

import pytest
from pathlib import Path
import yaml

from src.ma_registry import MARegistry


@pytest.fixture
def tmp_registry(tmp_path):
    """Create a registry with a temp file."""
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
        # Parent's divisions list updated
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
        """Divisions keep their own canonical name."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest src/tests/test_ma_registry.py -v`
Expected: All FAIL with `ImportError: cannot import name 'MARegistry' from 'src.ma_registry'`

- [ ] **Step 3: Implement MARegistry**

Create `src/ma_registry.py`:

```python
"""M&A registry: entity and corporate event management.

Entities are identified by short hash IDs (6 hex chars) with human-friendly
name slugs. Divisions use <parent_id>:<child_id> composite addressing.

All data persists to config/ma_registry.yaml.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from rag.config import MA_REGISTRY_PATH


def _generate_id(name: str) -> str:
    """Generate a 6-char hex ID from name + current timestamp."""
    raw = f"{name}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:6]


def _slugify(name: str) -> str:
    """Convert a company name to a URL-friendly slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


class MARegistry:
    """Manages entities and M&A events with YAML persistence."""

    def __init__(self, path: Path = MA_REGISTRY_PATH):
        self.path = path
        self.entities: list[dict] = []
        self.events: list[dict] = []
        if path.exists():
            self._load()

    def _load(self) -> None:
        with open(self.path) as f:
            data = yaml.safe_load(f) or {}
        self.entities = data.get("entities", [])
        self.events = data.get("events", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entities": self.entities, "events": self.events}
        with open(self.path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # --- Entity CRUD ---

    def add_entity(self, name: str, friendly: Optional[str] = None) -> dict:
        """Add a root entity. Returns the new entity dict."""
        entity_id = _generate_id(name)
        # Ensure uniqueness
        while any(e["id"] == entity_id for e in self.entities):
            entity_id = _generate_id(name + entity_id)
        entity = {
            "id": entity_id,
            "name": name,
            "friendly": friendly or _slugify(name),
        }
        self.entities.append(entity)
        self.save()
        return entity

    def add_division(
        self, parent_id: str, name: str, friendly: Optional[str] = None
    ) -> dict:
        """Add a division under a parent entity."""
        parent = self.get_entity(parent_id)
        if parent is None:
            raise ValueError(f"Parent entity '{parent_id}' not found")

        div = self.add_entity(name, friendly=friendly)
        div["parent"] = parent["id"]

        # Update parent's divisions list
        composite = f"{parent['id']}:{div['id']}"
        if "divisions" not in parent:
            parent["divisions"] = []
        parent["divisions"].append(composite)
        self.save()
        return div

    def get_entity(self, identifier: str) -> Optional[dict]:
        """Get entity by ID, friendly name, or composite key (parent:child).

        Supports:
          - "e7f3a2" (hash ID)
          - "apex-mfg" (friendly name)
          - "e7f3a2:b1c4d8" (composite division key by hash)
          - "apex-mfg:bright-star" (composite division key by friendly)
        """
        if ":" in identifier:
            parent_key, child_key = identifier.split(":", 1)
            parent = self.get_entity(parent_key)
            if parent is None:
                return None
            # Find child by ID or friendly
            for e in self.entities:
                if e.get("parent") == parent["id"]:
                    if e["id"] == child_key or e.get("friendly") == child_key:
                        return e
            return None

        # Direct lookup by id or friendly
        for e in self.entities:
            if e["id"] == identifier or e.get("friendly") == identifier:
                return e
        return None

    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity by ID. Updates parent's divisions list if applicable."""
        entity = self.get_entity(entity_id)
        if entity is None:
            return False

        # If it's a division, clean up parent's divisions list
        parent_id = entity.get("parent")
        if parent_id:
            parent = self.get_entity(parent_id)
            if parent and "divisions" in parent:
                composite = f"{parent['id']}:{entity['id']}"
                parent["divisions"] = [
                    d for d in parent["divisions"] if d != composite
                ]

        self.entities = [e for e in self.entities if e["id"] != entity["id"]]
        self.save()
        return True

    def list_entities(self) -> list[dict]:
        """Return all entities."""
        return list(self.entities)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest src/tests/test_ma_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ma_registry.py src/tests/test_ma_registry.py
git commit -m "feat: M&A registry entity model with ID generation and divisions"
```

---

## Task 3: M&A Registry — Events

**Files:**
- Modify: `src/ma_registry.py`
- Modify: `src/tests/test_ma_registry.py`

- [ ] **Step 1: Write failing tests for event CRUD**

Add to `src/tests/test_ma_registry.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest src/tests/test_ma_registry.py::TestEventCRUD -v`
Expected: FAIL with `AttributeError: 'MARegistry' object has no attribute 'add_event'`

- [ ] **Step 3: Implement event CRUD methods**

Add to `MARegistry` class in `src/ma_registry.py`:

```python
    # --- Event CRUD ---

    def add_event(
        self,
        event_type: str,
        date: str,
        acquirer_id: str,
        acquired_id: str,
        resulting_names: list[dict],
        co_merged: Optional[list[str]] = None,
        notes: str = "",
    ) -> dict:
        """Add an M&A event. Validates that referenced entity IDs exist."""
        # Validate entity IDs
        if self.get_entity(acquirer_id) is None:
            raise ValueError(f"Acquirer entity '{acquirer_id}' not found")
        if self.get_entity(acquired_id) is None:
            raise ValueError(f"Acquired entity '{acquired_id}' not found")
        if co_merged:
            for eid in co_merged:
                if self.get_entity(eid) is None:
                    raise ValueError(f"Co-merged entity '{eid}' not found")

        event_id = f"ma-{_generate_id(f'{acquirer_id}:{acquired_id}')}"
        # Ensure uniqueness
        while any(e["id"] == event_id for e in self.events):
            event_id = f"ma-{_generate_id(event_id)}"

        event = {
            "id": event_id,
            "type": event_type,
            "date": date,
            "acquirer": acquirer_id,
            "acquired": acquired_id,
            "resulting_names": resulting_names,
        }
        if co_merged:
            event["co_merged"] = co_merged
        if notes:
            event["notes"] = notes

        self.events.append(event)
        self.save()
        return event

    def get_event(self, event_id: str) -> Optional[dict]:
        """Get an event by ID."""
        for e in self.events:
            if e["id"] == event_id:
                return e
        return None

    def remove_event(self, event_id: str) -> bool:
        """Remove an event by ID."""
        before = len(self.events)
        self.events = [e for e in self.events if e["id"] != event_id]
        if len(self.events) < before:
            self.save()
            return True
        return False

    def list_events(self) -> list[dict]:
        """Return all events."""
        return list(self.events)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest src/tests/test_ma_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ma_registry.py src/tests/test_ma_registry.py
git commit -m "feat: M&A registry event CRUD with entity validation"
```

---

## Task 4: Chain Validator

**Files:**
- Create: `src/chain_validator.py`
- Create: `src/tests/test_chain_validator.py`

- [ ] **Step 1: Write failing tests for all 5 error conditions**

Create `src/tests/test_chain_validator.py`:

```python
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
        # A and B both appear in events — not orphaned
        assert not orphans

    def test_entity_in_no_event_is_orphaned(self, registry):
        registry.add_entity("Company A")
        registry.add_entity("Company B")
        # No events reference these entities
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
        # Only potential alert is orphan check — disabled
        errors = [a for a in alerts if a["severity"] == "error"]
        assert not errors
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest src/tests/test_chain_validator.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement chain_validator.py**

Create `src/chain_validator.py`:

```python
"""M&A chain validation: detect cycles, broken chains, temporal conflicts,
ambiguous forks, and orphaned entities.

Each detected issue produces an Alert with type, severity, message,
and recommended action.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from src.ma_registry import MARegistry


class AlertType(str, Enum):
    CYCLE = "cycle"
    BROKEN_CHAIN = "broken_chain"
    TEMPORAL_CONFLICT = "temporal_conflict"
    AMBIGUOUS_FORK = "ambiguous_fork"
    ORPHANED_ENTITY = "orphaned_entity"


def validate_registry(
    registry: MARegistry,
    check_orphans_against_data: bool = True,
    data_names: Optional[set[str]] = None,
) -> list[dict]:
    """Run all validations and return a list of alerts.

    Args:
        registry: The M&A registry to validate.
        check_orphans_against_data: If True, also check entities against
            data_names to find entities with zero occurrences.
        data_names: Set of all supplier names from data CSVs.

    Returns:
        List of alert dicts with keys: type, severity, message, action, details.
    """
    alerts: list[dict] = []
    alerts.extend(_check_cycles(registry))
    alerts.extend(_check_temporal_conflicts(registry))
    alerts.extend(_check_orphaned_entities(registry, check_orphans_against_data, data_names))
    return alerts


def _check_cycles(registry: MARegistry) -> list[dict]:
    """Detect cycles in acquirer→acquired graph using DFS."""
    # Build adjacency: acquirer -> [acquired]
    graph: dict[str, list[str]] = {}
    for event in registry.events:
        acquirer = event["acquirer"]
        acquired = event["acquired"]
        if acquirer == acquired:
            continue  # Rebrands (self-referencing) are not cycles
        graph.setdefault(acquirer, []).append(acquired)

    visited: set[str] = set()
    path: set[str] = set()
    alerts: list[dict] = []

    def dfs(node: str, chain: list[str]) -> None:
        if node in path:
            cycle_start = chain.index(node)
            cycle = chain[cycle_start:] + [node]
            names = []
            for eid in cycle:
                e = registry.get_entity(eid)
                names.append(e["name"] if e else eid)
            alerts.append({
                "type": AlertType.CYCLE,
                "severity": "error",
                "message": f"Cycle detected: {' -> '.join(names)}",
                "action": "Correct the M&A registry — one of these acquirer/acquired directions is wrong.",
                "details": {"cycle_entity_ids": cycle},
            })
            return
        if node in visited:
            return
        visited.add(node)
        path.add(node)
        for neighbor in graph.get(node, []):
            dfs(neighbor, chain + [node])
        path.discard(node)

    for start in graph:
        if start not in visited:
            dfs(start, [])

    return alerts


def _check_temporal_conflicts(registry: MARegistry) -> list[dict]:
    """Check if any resulting_name has first_seen before the event date."""
    alerts: list[dict] = []
    for event in registry.events:
        event_date = event["date"]
        for rn in event.get("resulting_names", []):
            first_seen = rn.get("first_seen")
            if first_seen and first_seen < event_date:
                alerts.append({
                    "type": AlertType.TEMPORAL_CONFLICT,
                    "severity": "warning",
                    "message": (
                        f"Temporal conflict in {event['id']}: "
                        f"'{rn['name']}' first_seen={first_seen} "
                        f"but event date={event_date}"
                    ),
                    "action": "Verify the first_seen date or the event date.",
                    "details": {
                        "event_id": event["id"],
                        "name": rn["name"],
                        "first_seen": first_seen,
                        "event_date": event_date,
                    },
                })
    return alerts


def _check_orphaned_entities(
    registry: MARegistry,
    check_against_data: bool,
    data_names: Optional[set[str]],
) -> list[dict]:
    """Find entities not referenced by any event."""
    # Collect all entity IDs referenced in events
    referenced: set[str] = set()
    for event in registry.events:
        referenced.add(event["acquirer"])
        referenced.add(event["acquired"])
        for eid in event.get("co_merged", []):
            referenced.add(eid)

    alerts: list[dict] = []
    for entity in registry.entities:
        eid = entity["id"]
        # Divisions are linked to parents, not events — skip them
        if entity.get("parent"):
            continue
        if eid not in referenced and len(registry.events) > 0:
            alerts.append({
                "type": AlertType.ORPHANED_ENTITY,
                "severity": "info",
                "message": (
                    f"Entity '{entity['name']}' ({eid}) is not referenced "
                    f"by any M&A event."
                ),
                "action": "Verify this entity is needed, or add it to an M&A event.",
                "details": {"entity_id": eid, "entity_name": entity["name"]},
            })

    return alerts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest src/tests/test_chain_validator.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chain_validator.py src/tests/test_chain_validator.py
git commit -m "feat: chain validator — cycle, temporal, orphan detection"
```

---

## Task 5: M&A Resolver — Chain Traversal

**Files:**
- Create: `src/ma_resolver.py`
- Create: `src/tests/test_ma_resolver.py`

- [ ] **Step 1: Write failing tests**

Create `src/tests/test_ma_resolver.py`:

```python
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
        """Order on the exact event date should resolve."""
        result = resolver.resolve("AQF Holdings", "2024-07-15")
        assert result.resolved

    def test_resolution_result_has_event_id(self, resolver):
        result = resolver.resolve("AQF Holdings", "2024-10-01")
        assert result.event_id is not None

    def test_resolution_result_has_chain(self, resolver):
        result = resolver.resolve("AQF Holdings", "2024-10-01")
        assert len(result.chain) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest src/tests/test_ma_resolver.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement MAResolver**

Create `src/ma_resolver.py`:

```python
"""M&A chain resolver: date-aware name resolution via registry traversal.

Given a supplier name and order date, searches the M&A registry for
matching resulting_names and traverses the chain to find the canonical
root entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.ma_registry import MARegistry


@dataclass
class ResolutionResult:
    """Result of an M&A chain resolution attempt."""
    resolved: bool
    canonical: Optional[str] = None
    confidence: float = 0.0
    source: str = "unresolved"
    event_id: Optional[str] = None
    chain: list[str] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)


class MAResolver:
    """Resolves supplier names via M&A registry chain traversal."""

    def __init__(self, registry: MARegistry):
        self.registry = registry
        self._build_index()

    def _build_index(self) -> None:
        """Build a reverse index: resulting_name -> (event, entity)."""
        self._name_to_events: dict[str, list[dict]] = {}
        for event in self.registry.events:
            for rn in event.get("resulting_names", []):
                name = rn["name"]
                self._name_to_events.setdefault(name, []).append({
                    "event": event,
                    "first_seen": rn.get("first_seen"),
                })

    def resolve(self, name: str, order_date: str) -> ResolutionResult:
        """Resolve a supplier name to its canonical root entity.

        Args:
            name: The supplier name to resolve.
            order_date: ISO date string (YYYY-MM-DD) of the order.

        Returns:
            ResolutionResult with canonical name if resolved.
        """
        matches = self._name_to_events.get(name, [])
        if not matches:
            return ResolutionResult(resolved=False)

        for match in matches:
            event = match["event"]
            event_date = event["date"]

            # Temporal filter: event must have occurred on or before order date
            if order_date < event_date:
                continue

            # Traverse to root: follow acquirer chain
            canonical_entity = self._traverse_to_root(event["acquirer"])
            if canonical_entity is None:
                continue

            chain = self._build_chain_path(name, event, canonical_entity)

            return ResolutionResult(
                resolved=True,
                canonical=canonical_entity["name"],
                confidence=1.0,
                source="ma_registry",
                event_id=event["id"],
                chain=chain,
            )

        return ResolutionResult(resolved=False)

    def _traverse_to_root(self, entity_id: str) -> Optional[dict]:
        """Follow the acquirer chain to the root entity.

        For simple cases, the acquirer IS the root. For chained M&A events
        (A acquires B, then C acquires A), follows the chain.
        """
        visited: set[str] = set()
        current_id = entity_id

        while current_id not in visited:
            visited.add(current_id)
            entity = self.registry.get_entity(current_id)
            if entity is None:
                return None

            # Check if this entity was itself acquired
            parent_event = None
            for event in self.registry.events:
                if event["acquired"] == current_id and event["acquirer"] != current_id:
                    parent_event = event
                    break

            if parent_event is None:
                return entity  # This is the root
            current_id = parent_event["acquirer"]

        # Cycle — should have been caught by validator
        return self.registry.get_entity(entity_id)

    def _build_chain_path(
        self, name: str, event: dict, root: dict
    ) -> list[str]:
        """Build a human-readable chain path."""
        acquirer = self.registry.get_entity(event["acquirer"])
        acquired = self.registry.get_entity(event["acquired"])
        chain = [name]
        if acquired and acquired["name"] != name:
            chain.append(f"({event['type']}: {acquired['name']})")
        if acquirer:
            chain.append(acquirer["name"])
        if root["id"] != event["acquirer"]:
            chain.append(f"-> {root['name']}")
        return chain
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest src/tests/test_ma_resolver.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ma_resolver.py src/tests/test_ma_resolver.py
git commit -m "feat: M&A resolver with date-aware chain traversal"
```

---

## Task 6: CLI — `ma` Subcommand Group

**Files:**
- Modify: `rag/cli.py`

- [ ] **Step 1: Add `ma` command group with list, add, show, remove, validate**

Add to `rag/cli.py` before the `if __name__` block:

```python
# --- M&A Registry Commands ---

@cli.group()
def ma():
    """Manage the M&A registry (entities, events, divisions)."""
    pass


@ma.command("list")
def ma_list():
    """List all entities and M&A events.

    Shows all registered companies, their divisions, and corporate
    events (acquisitions, mergers, rebrands, restructures).

    Example:
        caddi-cli ma list
    """
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)
    entities = reg.list_entities()
    events = reg.list_events()

    if not entities and not events:
        console.print("[dim]Registry is empty. Run 'caddi-cli ma add' to add entities.[/dim]")
        return

    if entities:
        table = Table(title="Entities")
        table.add_column("ID", style="cyan", width=8)
        table.add_column("Name")
        table.add_column("Friendly", style="dim")
        table.add_column("Type")
        for e in entities:
            etype = "division" if e.get("parent") else "root"
            if e.get("divisions"):
                etype = f"root ({len(e['divisions'])} div)"
            table.add_row(e["id"], e["name"], e.get("friendly", ""), etype)
        console.print(table)

    if events:
        console.print()
        table = Table(title="M&A Events")
        table.add_column("ID", style="cyan")
        table.add_column("Type")
        table.add_column("Date")
        table.add_column("Acquirer")
        table.add_column("Acquired")
        table.add_column("Names", justify="right")
        for ev in events:
            acq_entity = reg.get_entity(ev["acquirer"])
            acd_entity = reg.get_entity(ev["acquired"])
            acq_name = acq_entity["name"] if acq_entity else ev["acquirer"]
            acd_name = acd_entity["name"] if acd_entity else ev["acquired"]
            n_names = len(ev.get("resulting_names", []))
            table.add_row(ev["id"], ev["type"], ev["date"], acq_name, acd_name, str(n_names))
        console.print(table)


@ma.command("add")
@click.option("--type", "event_type", type=click.Choice(["acquisition", "merger", "rebrand", "restructure"]))
@click.option("--date", "event_date", help="Event date (YYYY-MM-DD)")
@click.option("--acquirer", help="Acquirer entity name (creates if new)")
@click.option("--acquired", help="Acquired entity name (creates if new)")
@click.option("--resulting-name", "resulting_names", multiple=True, help="Post-event name variant (repeatable)")
@click.option("--notes", default="", help="Optional notes")
@click.option("--entity-only", is_flag=True, help="Just add an entity, no event")
@click.option("--name", "entity_name", help="Entity name (with --entity-only)")
def ma_add(event_type, event_date, acquirer, acquired, resulting_names, notes, entity_only, entity_name):
    """Add an entity or M&A event to the registry.

    Examples:
        # Add just an entity
        caddi-cli ma add --entity-only --name "Apex Manufacturing"

        # Add an acquisition event
        caddi-cli ma add --type acquisition --date 2024-07-15 \\
            --acquirer "Apex Manufacturing" --acquired "QuickFab Industries" \\
            --resulting-name "AQF Holdings" --resulting-name "Apex-QuickFab Industries"

        # Interactive mode (no options)
        caddi-cli ma add
    """
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)

    if entity_only:
        name = entity_name or click.prompt("Entity name")
        friendly = click.prompt("Friendly name (or Enter for auto)", default="", show_default=False)
        entity = reg.add_entity(name, friendly=friendly or None)
        console.print(f"[green]Created entity:[/green] {entity['id']} ({entity['friendly']})")
        return

    # Interactive if no options provided
    if not event_type:
        event_type = click.prompt("Event type", type=click.Choice(["acquisition", "merger", "rebrand", "restructure"]))
    if not event_date:
        event_date = click.prompt("Date (YYYY-MM-DD)")
    if not acquirer:
        acquirer = click.prompt("Acquirer (surviving entity)")
    if not acquired:
        acquired = click.prompt("Acquired entity")

    # Find or create entities
    def _find_or_create(name):
        for e in reg.list_entities():
            if e["name"].lower() == name.lower() or e.get("friendly") == name.lower():
                return e
        return reg.add_entity(name)

    acq_entity = _find_or_create(acquirer)
    acd_entity = _find_or_create(acquired)

    # Collect resulting names
    rn_list = [{"name": n} for n in resulting_names]
    if not rn_list:
        while True:
            n = click.prompt("Resulting name (or Enter to finish)", default="", show_default=False)
            if not n:
                break
            fs = click.prompt(f"  First seen date for '{n}' (or Enter to skip)", default="", show_default=False)
            entry = {"name": n}
            if fs:
                entry["first_seen"] = fs
            rn_list.append(entry)

    event = reg.add_event(
        event_type=event_type,
        date=event_date,
        acquirer_id=acq_entity["id"],
        acquired_id=acd_entity["id"],
        resulting_names=rn_list,
        notes=notes,
    )
    console.print(f"[green]Created event:[/green] {event['id']} ({event_type})")


@ma.command("show")
@click.argument("identifier")
def ma_show(identifier):
    """Show details of an entity or event.

    IDENTIFIER can be an entity ID, friendly name, composite key,
    or event ID.

    Examples:
        caddi-cli ma show e7f3a2
        caddi-cli ma show apex-mfg
        caddi-cli ma show apex-mfg:bright-star
        caddi-cli ma show ma-8f2a1b
    """
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH
    import json

    reg = MARegistry(path=MA_REGISTRY_PATH)

    # Try entity first
    entity = reg.get_entity(identifier)
    if entity:
        console.print(Panel(
            json.dumps(entity, indent=2, default=str),
            title=f"Entity: {entity['name']}",
            border_style="cyan",
        ))
        return

    # Try event
    event = reg.get_event(identifier)
    if event:
        acq = reg.get_entity(event["acquirer"])
        acd = reg.get_entity(event["acquired"])
        event_display = dict(event)
        event_display["acquirer_name"] = acq["name"] if acq else "?"
        event_display["acquired_name"] = acd["name"] if acd else "?"
        console.print(Panel(
            json.dumps(event_display, indent=2, default=str),
            title=f"Event: {event['id']} ({event['type']})",
            border_style="yellow",
        ))
        return

    console.print(f"[red]'{identifier}' not found as entity or event.[/red]")


@ma.command("remove")
@click.argument("identifier")
@click.option("--force", is_flag=True, help="Skip confirmation")
def ma_remove(identifier, force):
    """Remove an entity or event.

    Examples:
        caddi-cli ma remove e7f3a2
        caddi-cli ma remove ma-8f2a1b --force
    """
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)

    # Try event first
    event = reg.get_event(identifier)
    if event:
        acq = reg.get_entity(event["acquirer"])
        acd = reg.get_entity(event["acquired"])
        label = f"{event['id']} ({acq['name'] if acq else '?'} {event['type']} {acd['name'] if acd else '?'})"
        if not force:
            click.confirm(f"Remove event {label}?", abort=True)
        reg.remove_event(identifier)
        console.print(f"[green]Removed event {identifier}.[/green]")
        return

    # Try entity
    entity = reg.get_entity(identifier)
    if entity:
        if not force:
            click.confirm(f"Remove entity '{entity['name']}' ({entity['id']})?", abort=True)
        reg.remove_entity(entity["id"])
        console.print(f"[green]Removed entity {entity['id']}.[/green]")
        return

    console.print(f"[red]'{identifier}' not found.[/red]")


@ma.command("validate")
def ma_validate():
    """Validate the M&A registry for errors.

    Checks for cycles, temporal conflicts, and orphaned entities.

    Example:
        caddi-cli ma validate
    """
    from src.ma_registry import MARegistry
    from src.chain_validator import validate_registry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)
    if not reg.events:
        console.print("[dim]No events to validate.[/dim]")
        return

    console.print(f"Checking {len(reg.events)} events...")
    alerts = validate_registry(reg, check_orphans_against_data=False)

    errors = [a for a in alerts if a["severity"] == "error"]
    warnings = [a for a in alerts if a["severity"] == "warning"]
    infos = [a for a in alerts if a["severity"] == "info"]

    for a in errors:
        console.print(f"  [red]ERROR:[/red] {a['message']}")
        console.print(f"    [dim]Action: {a['action']}[/dim]")
    for a in warnings:
        console.print(f"  [yellow]WARNING:[/yellow] {a['message']}")
        console.print(f"    [dim]Action: {a['action']}[/dim]")
    for a in infos:
        console.print(f"  [dim]INFO: {a['message']}[/dim]")

    if not alerts:
        console.print("[green]OK: No issues found.[/green]")
    else:
        console.print(f"\n{len(errors)} errors, {len(warnings)} warnings, {len(infos)} info.")
```

- [ ] **Step 2: Run existing tests to verify nothing is broken**

Run: `.venv/bin/pytest --tb=short -q`
Expected: All existing tests pass + new tests pass

- [ ] **Step 3: Commit**

```bash
git add rag/cli.py
git commit -m "feat: caddi-cli ma subcommand group (list, add, show, remove, validate)"
```

---

## Task 7: Demo Data Generator

**Files:**
- Create: `src/demo_generator.py`
- Create: `src/tests/test_demo_generator.py`

- [ ] **Step 1: Write failing tests**

Create `src/tests/test_demo_generator.py`:

```python
"""Tests for demo data generator."""

import pytest
import pandas as pd
from pathlib import Path

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
    import yaml
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
        """Orders for post-M&A names should have dates after the event."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest src/tests/test_demo_generator.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement demo_generator.py**

Create `src/demo_generator.py`:

```python
"""Generate synthetic demo CSVs from M&A registry and test scenarios.

Creates orders, inspections, and RFQs with supplier names from test scenarios,
ensuring temporal consistency with M&A event dates.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from src.ma_registry import MARegistry

# Real Hoth part data for realistic demo rows
PARTS = [
    ("HX-5520", "Aluminum Heat Exchanger", 800.0, 1200.0),
    ("CTRL-9985", "PLC Control Module", 350.0, 500.0),
    ("FAN-2436", "36 inch Axial Fan", 180.0, 280.0),
    ("BRKT-1005", "Heavy Duty Mount", 15.0, 30.0),
    ("DAMPER-3305", "Pneumatic Damper 36 inch", 200.0, 350.0),
    ("BEARING-9905", "Heavy Duty Bearing Set", 60.0, 100.0),
    ("PANEL-8820", "Stainless Control Panel", 220.0, 320.0),
    ("SENSOR-4401", "Temperature Sensor Probe", 40.0, 80.0),
]


def load_test_scenarios(path: Path) -> list[dict]:
    """Load test scenarios from YAML."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("scenarios", [])


def generate_demo_data(
    registry: MARegistry,
    scenarios_path: Path,
    output_dir: Path,
    orders_per_scenario: int = 4,
    seed: int = 42,
) -> dict[str, Path]:
    """Generate synthetic demo CSVs.

    Args:
        registry: M&A registry for temporal event dates.
        scenarios_path: Path to test_scenarios.yaml.
        output_dir: Directory to write demo CSVs.
        orders_per_scenario: Number of orders per test scenario.
        seed: Random seed for reproducibility.

    Returns:
        Dict of {filename: path} for generated CSVs.
    """
    random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = load_test_scenarios(scenarios_path)

    # Build a map of event dates for temporal consistency
    event_dates: dict[str, str] = {}  # resulting_name -> event_date
    for event in registry.events:
        for rn in event.get("resulting_names", []):
            event_dates[rn["name"]] = event["date"]

    # Generate orders
    orders = []
    order_num = 1
    for sc in scenarios:
        name = sc["input_name"]
        min_date = event_dates.get(name, "2021-10-01")

        for _ in range(orders_per_scenario):
            # Generate a date after the M&A event (if applicable)
            base = datetime.strptime(min_date, "%Y-%m-%d")
            offset = random.randint(1, 180)
            order_date = base + timedelta(days=offset)
            promised = order_date + timedelta(days=random.randint(14, 60))
            delivered = promised + timedelta(days=random.randint(-5, 15))

            part = random.choice(PARTS)
            qty = random.randint(10, 300)
            price = round(random.uniform(part[2], part[3]), 2)

            orders.append({
                "order_id": f"PO-DEMO-{order_num:03d}",
                "supplier_name": name,
                "part_number": part[0],
                "part_description": part[1],
                "order_date": order_date.strftime("%Y-%m-%d"),
                "promised_date": promised.strftime("%Y-%m-%d"),
                "actual_delivery_date": delivered.strftime("%Y-%m-%d"),
                "quantity": qty,
                "unit_price": price,
                "po_amount": round(qty * price, 2),
            })
            order_num += 1

    orders_df = pd.DataFrame(orders)
    orders_path = output_dir / "demo_orders.csv"
    orders_df.to_csv(orders_path, index=False)

    # Generate inspections (1 per 2 orders)
    inspections = []
    insp_num = 1
    for _, order in orders_df.iterrows():
        if random.random() < 0.5:
            continue
        parts_inspected = random.randint(5, int(order["quantity"]))
        reject_rate = random.uniform(0, 0.15)
        parts_rejected = int(parts_inspected * reject_rate)
        reasons = ["Passed", "Surface scratches", "Dimensional error",
                    "Weld porosity", "Sensor drift"]
        reason = "Passed" if parts_rejected == 0 else random.choice(reasons[1:])
        inspections.append({
            "inspection_id": f"INS-DEMO-{insp_num:03d}",
            "order_id": order["order_id"],
            "inspection_date": order["actual_delivery_date"],
            "parts_inspected": parts_inspected,
            "parts_rejected": parts_rejected,
            "rejection_reason": reason,
            "rework_required": "Yes" if parts_rejected > 0 and random.random() < 0.5 else "No",
        })
        insp_num += 1

    insp_df = pd.DataFrame(inspections)
    insp_path = output_dir / "demo_inspections.csv"
    insp_df.to_csv(insp_path, index=False)

    # Generate RFQs (1 per 3 scenarios)
    rfqs = []
    rfq_num = 1
    for sc in scenarios:
        if random.random() < 0.3:
            continue
        part = random.choice(PARTS)
        name = sc["input_name"]
        min_date = event_dates.get(name, "2021-10-01")
        base = datetime.strptime(min_date, "%Y-%m-%d")
        quote_date = base + timedelta(days=random.randint(1, 90))

        rfqs.append({
            "rfq_id": f"RFQ-DEMO-{rfq_num:03d}",
            "supplier_name": name,
            "part_description": part[1],
            "quote_date": quote_date.strftime("%Y-%m-%d"),
            "quoted_price": round(random.uniform(part[2], part[3] * 1.2), 2),
            "lead_time_weeks": random.randint(2, 12),
            "notes": f"Demo scenario {sc['id']} (tier {sc['difficulty']})",
        })
        rfq_num += 1

    rfq_df = pd.DataFrame(rfqs)
    rfq_path = output_dir / "demo_rfq.csv"
    rfq_df.to_csv(rfq_path, index=False)

    return {
        "demo_orders.csv": orders_path,
        "demo_inspections.csv": insp_path,
        "demo_rfq.csv": rfq_path,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest src/tests/test_demo_generator.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/demo_generator.py src/tests/test_demo_generator.py
git commit -m "feat: demo data generator with temporal consistency"
```

---

## Task 8: Benchmark — Precision/Recall by Tier

**Files:**
- Create: `src/benchmark.py`
- Create: `src/tests/test_benchmark.py`

- [ ] **Step 1: Write failing tests**

Create `src/tests/test_benchmark.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest src/tests/test_benchmark.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement benchmark.py**

Create `src/benchmark.py`:

```python
"""Benchmarking: run resolution pipeline against ground truth scenarios
and compute precision/recall metrics by difficulty tier and category."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


@dataclass
class BenchmarkResult:
    """Result of resolving one test scenario."""
    input_name: str
    expected_canonical: str
    resolved_canonical: Optional[str]
    was_resolved: bool
    difficulty: int
    category: str = ""
    source: str = ""  # clustering, ma_registry, unresolved


def compute_metrics(results: list[BenchmarkResult]) -> dict:
    """Compute precision, recall, F1 overall and by difficulty tier.

    Precision = correct_resolutions / total_attempted_resolutions
    Recall = correct_resolutions / total_scenarios
    """
    if not results:
        return {
            "overall": {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                        "total": 0, "resolved": 0, "correct": 0},
            "by_tier": {},
            "by_category": {},
        }

    def _calc(subset: list[BenchmarkResult]) -> dict:
        total = len(subset)
        resolved = [r for r in subset if r.was_resolved]
        correct = [r for r in resolved if r.resolved_canonical == r.expected_canonical]
        p = len(correct) / len(resolved) if resolved else 0.0
        r = len(correct) / total if total else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "total": total,
            "resolved": len(resolved),
            "correct": len(correct),
        }

    # Overall
    overall = _calc(results)

    # By tier
    by_tier: dict[int, dict] = {}
    tiers = defaultdict(list)
    for r in results:
        tiers[r.difficulty].append(r)
    for tier in sorted(tiers.keys()):
        by_tier[tier] = _calc(tiers[tier])

    # By category
    by_category: dict[str, dict] = {}
    categories = defaultdict(list)
    for r in results:
        if r.category:
            categories[r.category].append(r)
    for cat in sorted(categories.keys()):
        by_category[cat] = _calc(categories[cat])

    return {
        "overall": overall,
        "by_tier": by_tier,
        "by_category": by_category,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest src/tests/test_benchmark.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/benchmark.py src/tests/test_benchmark.py
git commit -m "feat: benchmark metrics — precision/recall by difficulty tier"
```

---

## Task 9: CLI — `demo` Subcommand Group

**Files:**
- Modify: `rag/cli.py`

- [ ] **Step 1: Add demo generate, run, report commands**

Add to `rag/cli.py` before the `if __name__` block:

```python
# --- Demo Commands ---

@cli.group()
def demo():
    """Generate demo data, run benchmarks, view reports."""
    pass


@demo.command("generate")
def demo_generate():
    """Generate synthetic demo CSVs from M&A registry and test scenarios.

    Reads config/ma_registry.yaml and config/test_scenarios.yaml,
    creates data/demo/ with demo_orders.csv, demo_inspections.csv, demo_rfq.csv.

    Example:
        caddi-cli demo generate
    """
    from src.ma_registry import MARegistry
    from src.demo_generator import generate_demo_data
    from rag.config import MA_REGISTRY_PATH, TEST_SCENARIOS_PATH, DEMO_DIR

    if not MA_REGISTRY_PATH.exists():
        console.print("[red]No M&A registry found. Run 'caddi-cli ma add' first.[/red]")
        return
    if not TEST_SCENARIOS_PATH.exists():
        console.print("[red]No test scenarios found at config/test_scenarios.yaml[/red]")
        return

    reg = MARegistry(path=MA_REGISTRY_PATH)
    console.print(f"Reading ma_registry.yaml ({len(reg.events)} events)")

    files = generate_demo_data(
        registry=reg,
        scenarios_path=TEST_SCENARIOS_PATH,
        output_dir=DEMO_DIR,
    )

    console.print("[green]Generated:[/green]")
    for name, path in files.items():
        import pandas as pd
        df = pd.read_csv(path)
        console.print(f"  {path} ({len(df)} rows)")


@demo.command("run")
def demo_run():
    """Run the full resolution pipeline on demo data and report metrics.

    Resolves all demo supplier names using the three-stage pipeline
    (clustering -> M&A registry -> human escalation) and compares
    against ground truth from test_scenarios.yaml.

    Example:
        caddi-cli demo run
    """
    from src.ma_registry import MARegistry
    from src.ma_resolver import MAResolver
    from src.demo_generator import load_test_scenarios
    from src.benchmark import BenchmarkResult, compute_metrics
    from src.supplier_clustering import ClusterMethod, cluster_names
    from rag.config import MA_REGISTRY_PATH, TEST_SCENARIOS_PATH

    if not TEST_SCENARIOS_PATH.exists():
        console.print("[red]No test scenarios. Run 'caddi-cli demo generate' first.[/red]")
        return

    scenarios = load_test_scenarios(TEST_SCENARIOS_PATH)
    console.print(f"Resolving {len(scenarios)} test scenarios...\n")

    # Set up resolver
    reg = MARegistry(path=MA_REGISTRY_PATH) if MA_REGISTRY_PATH.exists() else None
    resolver = MAResolver(reg) if reg else None

    # Collect all input names for clustering
    all_names = [sc["input_name"] for sc in scenarios]
    # Add known canonical names for clustering context
    canonical_names = list(set(sc["expected_canonical"] for sc in scenarios))
    cluster_input = all_names + canonical_names

    clusters = cluster_names(cluster_input, method=ClusterMethod.PIPELINE)
    lookup = {}
    for canonical, variants in clusters.items():
        for v in variants:
            lookup[v] = canonical

    results = []
    for sc in scenarios:
        name = sc["input_name"]
        expected = sc["expected_canonical"]
        difficulty = sc["difficulty"]
        category = sc.get("category", "")

        # Stage 1: clustering
        cluster_result = lookup.get(name)
        if cluster_result and cluster_result == expected:
            results.append(BenchmarkResult(
                name, expected, cluster_result, True, difficulty, category, "clustering"))
            continue

        # Stage 2: M&A resolver
        if resolver:
            # Use a date well after any possible event for demo purposes
            ma_result = resolver.resolve(name, "2026-01-01")
            if ma_result.resolved:
                results.append(BenchmarkResult(
                    name, expected, ma_result.canonical, True, difficulty, category, "ma_registry"))
                continue

        # Stage 3: unresolved
        resolved_name = cluster_result if cluster_result else None
        was_resolved = resolved_name is not None
        results.append(BenchmarkResult(
            name, expected, resolved_name, was_resolved, difficulty, category, "unresolved"))

    metrics = compute_metrics(results)

    # Display results
    table = Table(title="Entity Resolution Results")
    table.add_column("Difficulty", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Resolved", justify="right")
    table.add_column("Prec.", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("F1", justify="right")

    for tier in sorted(metrics["by_tier"].keys()):
        m = metrics["by_tier"][tier]
        tier_names = {1: "easy", 2: "medium", 3: "hard", 4: "advers"}
        label = f"{tier} ({tier_names.get(tier, '?')})"
        table.add_row(
            label, str(m["total"]), f"{m['correct']}/{m['total']}",
            f"{m['precision']:.0%}", f"{m['recall']:.0%}", f"{m['f1']:.2f}")

    table.add_section()
    o = metrics["overall"]
    table.add_row(
        "[bold]Overall[/bold]", str(o["total"]), f"{o['correct']}/{o['total']}",
        f"{o['precision']:.0%}", f"{o['recall']:.0%}", f"{o['f1']:.2f}")

    console.print(table)

    # Show unresolved
    unresolved = [r for r in results if not r.was_resolved or r.resolved_canonical != r.expected_canonical]
    if unresolved:
        console.print(f"\n[yellow]Unresolved/incorrect ({len(unresolved)}):[/yellow]")
        for r in unresolved:
            status = "wrong" if r.was_resolved else "unresolved"
            console.print(f"  {r.input_name} -> expected '{r.expected_canonical}', got '{r.resolved_canonical}' ({status}, tier {r.difficulty})")
```

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add rag/cli.py
git commit -m "feat: caddi-cli demo subcommand group (generate, run)"
```

---

## Task 10: Pre-built Demo Data

**Files:**
- Create: `config/ma_registry.yaml` (pre-populated)
- Create: `config/test_scenarios.yaml` (pre-populated)

- [ ] **Step 1: Create the M&A registry with 4 events**

Create `config/ma_registry.yaml` using the CLI:

```bash
# Create entities and events
.venv/bin/python -c "
from src.ma_registry import MARegistry
from rag.config import MA_REGISTRY_PATH

reg = MARegistry(path=MA_REGISTRY_PATH)

# Root entities
apex = reg.add_entity('Apex Manufacturing', friendly='apex-mfg')
qf = reg.add_entity('QuickFab Industries', friendly='quickfab')
pt = reg.add_entity('Precision Thermal Co', friendly='precision-thermal')
sm = reg.add_entity('Stellar Metalworks', friendly='stellar')
tf = reg.add_entity('TitanForge LLC', friendly='titanforge')
af = reg.add_entity('AeroFlow Systems', friendly='aeroflow')

# Divisions
reg.add_division(apex['id'], 'Bright Star Foundrys', friendly='bright-star')
reg.add_division(apex['id'], 'Juniper Racing Parts', friendly='juniper-racing')
reg.add_division(apex['id'], 'Knight Fastener Fabrication Services', friendly='knight-fastener')

# Events
reg.add_event('acquisition', '2024-07-15', apex['id'], qf['id'],
              [{'name': 'Apex-QuickFab Industries', 'first_seen': '2024-08-01'},
               {'name': 'AQF Holdings', 'first_seen': '2024-09-15'},
               {'name': 'Apex Manufacturing - QuickFab Division', 'first_seen': '2024-08-01'}],
              notes='QuickFab absorbed into Apex supply division')

reg.add_event('rebrand', '2025-01-01', pt['id'], pt['id'],
              [{'name': 'Zenith Thermal Solutions', 'first_seen': '2025-01-15'},
               {'name': 'Zenith Thermal', 'first_seen': '2025-02-01'}],
              notes='Full rebrand, zero token overlap')

reg.add_event('merger', '2023-06-01', sm['id'], tf['id'],
              [{'name': 'StellarForge Industries', 'first_seen': '2023-07-01'},
               {'name': 'SF Industries', 'first_seen': '2023-08-01'}],
              co_merged=[sm['id'], tf['id']],
              notes='Equal merger')

reg.add_event('restructure', '2024-01-15', af['id'], af['id'],
              [{'name': 'AeroFlow Technologies', 'first_seen': '2024-02-01'},
               {'name': 'AeroFlow Tech', 'first_seen': '2024-03-01'}],
              notes='Corporate restructuring')

print(f'Created {len(reg.entities)} entities, {len(reg.events)} events')
"
```

- [ ] **Step 2: Create test scenarios YAML**

Write `config/test_scenarios.yaml` with scenarios spanning all 4 difficulty tiers (the exact content from the spec section 3.3, plus additional scenarios to reach ~30 total).

- [ ] **Step 3: Generate demo data**

```bash
./caddi-cli demo generate
```

- [ ] **Step 4: Validate**

```bash
./caddi-cli ma validate
./caddi-cli demo run
```

- [ ] **Step 5: Commit**

```bash
git add config/ma_registry.yaml config/test_scenarios.yaml data/demo/
git commit -m "data: pre-built M&A registry, test scenarios, and demo CSVs"
```

---

## Task 11: Web Visualization

**Files:**
- Create: `web/index.html`
- Create: `web/graph.js`
- Create: `web/style.css`
- Modify: `rag/cli.py` (add `viz` command)

- [ ] **Step 1: Create the HTML shell**

Create `web/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CADDi Supply Chain — Entity Graph</title>
    <link rel="stylesheet" href="style.css">
    <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
    <div id="app">
        <div id="sidebar">
            <h2>Entity Graph</h2>
            <div id="filters">
                <label>Difficulty: <select id="tier-filter">
                    <option value="all">All</option>
                    <option value="1">1 (Easy)</option>
                    <option value="2">2 (Medium)</option>
                    <option value="3">3 (Hard)</option>
                    <option value="4">4 (Adversarial)</option>
                </select></label>
                <label>Source: <select id="source-filter">
                    <option value="all">All</option>
                    <option value="clustering">Clustering</option>
                    <option value="ma_registry">M&A Registry</option>
                    <option value="confirmed">Confirmed</option>
                </select></label>
                <label>Search: <input id="search" type="text" placeholder="Type a name..."></label>
            </div>
            <div id="alerts-panel">
                <h3>Alerts</h3>
                <div id="alerts-list"></div>
            </div>
            <div id="detail-panel">
                <h3>Details</h3>
                <div id="detail-content"><em>Click a node or edge</em></div>
            </div>
        </div>
        <div id="graph-container">
            <svg id="graph"></svg>
        </div>
    </div>
    <script src="graph.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create the CSS**

Create `web/style.css` with layout for sidebar + graph canvas, node/edge styling, and alert panel.

- [ ] **Step 3: Create graph.js with D3.js force-directed layout**

Create `web/graph.js` that:
- Fetches `/api/graph` for node/edge data
- Renders force-directed graph with nodes colored by entity type (canonical, variant, division, M&A resulting)
- Edge width = confidence score, color = green/yellow/red by threshold
- M&A edges dashed, labeled with event ID + date
- Division edges thin solid, labeled "division of"
- Hover shows tooltip with scores
- Click selects and shows details in sidebar
- Filter controls update graph live
- Search highlights matching nodes

- [ ] **Step 4: Add `viz` command to CLI**

Add to `rag/cli.py`:

```python
@cli.command()
@click.option("--port", default=8095, help="Port for the web server")
@click.option("--no-browser", is_flag=True, help="Don't auto-open browser")
def viz(port, no_browser):
    """Launch the web visualization of the entity graph.

    Starts a local web server and opens the browser to show the
    interactive supplier name relationship graph.

    Example:
        caddi-cli viz
        caddi-cli viz --port 9090
    """
    import http.server
    import json
    import threading
    import webbrowser
    from functools import partial

    from src.ma_registry import MARegistry
    from src.supplier_clustering import ClusterMethod, cluster_names, compute_edge_scores
    from src.human_review import apply_human_overrides, load_confirmed_scores
    from src.chain_validator import validate_registry
    from rag.config import (
        MA_REGISTRY_PATH, CONFIRMED_MAPPINGS_PATH, DATA_DIR, WEB_DIR,
    )

    # Build graph data
    import pandas as pd
    all_names = []
    for csv_file in sorted(DATA_DIR.glob("*.csv")):
        df = pd.read_csv(csv_file)
        if "supplier_name" in df.columns:
            all_names.extend(df["supplier_name"].tolist())

    clusters = cluster_names(all_names, method=ClusterMethod.PIPELINE)
    clusters = apply_human_overrides(clusters, confirmed_path=CONFIRMED_MAPPINGS_PATH)
    confirmed_scores = load_confirmed_scores(CONFIRMED_MAPPINGS_PATH)
    edge_scores = compute_edge_scores(clusters, confirmed_scores=confirmed_scores)

    # M&A data
    reg = MARegistry(path=MA_REGISTRY_PATH) if MA_REGISTRY_PATH.exists() else None
    alerts = validate_registry(reg, check_orphans_against_data=False) if reg else []

    # Build JSON for the frontend
    graph_data = _build_graph_json(clusters, edge_scores, reg, alerts, all_names)

    class GraphHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WEB_DIR), **kwargs)

        def do_GET(self):
            if self.path == "/api/graph":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(graph_data).encode())
            else:
                super().do_GET()

    def _build_graph_json(clusters, edge_scores, reg, alerts, all_names):
        nodes = []
        edges = []
        node_ids = set()

        for canonical, members in clusters.items():
            if canonical not in node_ids:
                nodes.append({
                    "id": canonical, "type": "canonical",
                    "count": all_names.count(canonical),
                })
                node_ids.add(canonical)

            for variant in members:
                if variant == canonical:
                    continue
                if variant not in node_ids:
                    nodes.append({
                        "id": variant, "type": "variant",
                        "count": all_names.count(variant),
                    })
                    node_ids.add(variant)

                scores = edge_scores.get(canonical, {}).get(variant, {})
                edges.append({
                    "source": variant, "target": canonical,
                    "type": "clustering",
                    "jaccard": scores.get("jaccard", 0),
                    "embedding": scores.get("embedding", 0),
                    "combined": scores.get("combined", 0),
                    "source_type": scores.get("source", "auto"),
                })

        # Add M&A edges
        if reg:
            for event in reg.events:
                acq = reg.get_entity(event["acquirer"])
                acd = reg.get_entity(event["acquired"])
                if not acq or not acd:
                    continue

                for rn in event.get("resulting_names", []):
                    rn_name = rn["name"]
                    if rn_name not in node_ids:
                        nodes.append({"id": rn_name, "type": "ma_resulting", "count": 0})
                        node_ids.add(rn_name)
                    edges.append({
                        "source": rn_name, "target": acq["name"],
                        "type": "ma",
                        "event_id": event["id"],
                        "event_type": event["type"],
                        "event_date": event["date"],
                        "combined": 1.0,
                    })

            # Division edges
            for entity in reg.entities:
                if entity.get("parent"):
                    parent = reg.get_entity(entity["parent"])
                    if parent:
                        if entity["name"] not in node_ids:
                            nodes.append({"id": entity["name"], "type": "division", "count": 0})
                            node_ids.add(entity["name"])
                        edges.append({
                            "source": entity["name"], "target": parent["name"],
                            "type": "division",
                            "combined": 1.0,
                        })

        return {"nodes": nodes, "edges": edges, "alerts": alerts}

    console.print(f"[green]Starting visualization server on port {port}...[/green]")
    console.print(f"  Graph: {len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges")
    console.print(f"  Alerts: {len(graph_data['alerts'])}")
    console.print(f"\n  Open: [bold]http://localhost:{port}[/bold]")
    console.print("  Press Ctrl+C to stop.\n")

    if not no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    server = http.server.HTTPServer(("", port), GraphHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")
```

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add web/ rag/cli.py
git commit -m "feat: web visualization with D3.js force-directed graph + caddi-cli viz"
```

---

## Task 12: Docker Deployment

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Update Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || true

# Copy source
COPY . .

# Install the package
RUN pip install --no-cache-dir -e ".[dev]"

# Pre-download the embedding model so it's cached in the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8095

ENTRYPOINT ["./caddi-cli"]
CMD ["--help"]
```

- [ ] **Step 2: Build and test**

```bash
docker build -t caddi-demo .
docker run --rm caddi-demo --help
docker run --rm caddi-demo ma list
docker run --rm -p 8095:8095 caddi-demo viz --no-browser
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "docker: single-image deployment with pre-downloaded embeddings"
```

---

## Task 13: Full Integration Test + Push

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/pytest --tb=short -q
```
Expected: All tests pass (existing 110 + new ~40 = ~150 total)

- [ ] **Step 2: Run the full demo flow**

```bash
./caddi-cli ma list
./caddi-cli ma validate
./caddi-cli demo generate
./caddi-cli demo run
./caddi-cli mappings
```

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```
