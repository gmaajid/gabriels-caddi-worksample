"""M&A chain validation: detect cycles, broken chains, temporal conflicts,
ambiguous forks, and orphaned entities."""

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
    alerts: list[dict] = []
    alerts.extend(_check_cycles(registry))
    alerts.extend(_check_temporal_conflicts(registry))
    alerts.extend(_check_orphaned_entities(registry, check_orphans_against_data, data_names))
    return alerts


def _check_cycles(registry: MARegistry) -> list[dict]:
    """Detect cycles in acquirer->acquired graph using DFS."""
    graph: dict[str, list[str]] = {}
    for event in registry.events:
        acquirer = event["acquirer"]
        acquired = event["acquired"]
        if acquirer == acquired:
            continue  # Rebrands are not cycles
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
    referenced: set[str] = set()
    for event in registry.events:
        referenced.add(event["acquirer"])
        referenced.add(event["acquired"])
        for eid in event.get("co_merged", []):
            referenced.add(eid)

    # Only suppress orphan reporting when every entity is referenced by events
    # (i.e. there are events AND every entity appears in at least one).
    # When check_against_data=False we always report unreferenced entities.
    has_any_events = len(registry.events) > 0

    alerts: list[dict] = []
    for entity in registry.entities:
        eid = entity["id"]
        if entity.get("parent"):
            continue  # Divisions are linked to parents, not events
        if eid not in referenced and (has_any_events or not check_against_data):
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
