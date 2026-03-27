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
    resolved: bool
    canonical: Optional[str] = None
    confidence: float = 0.0
    source: str = "unresolved"
    event_id: Optional[str] = None
    chain: list[str] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)


class MAResolver:
    def __init__(self, registry: MARegistry):
        self.registry = registry
        self._build_index()

    def _build_index(self) -> None:
        self._name_to_events: dict[str, list[dict]] = {}
        for event in self.registry.events:
            for rn in event.get("resulting_names", []):
                name = rn["name"]
                self._name_to_events.setdefault(name, []).append({
                    "event": event,
                    "first_seen": rn.get("first_seen"),
                })

    def resolve(self, name: str, order_date: str) -> ResolutionResult:
        matches = self._name_to_events.get(name, [])
        if not matches:
            return ResolutionResult(resolved=False)

        for match in matches:
            event = match["event"]
            event_date = event["date"]
            if order_date < event_date:
                continue
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
        visited: set[str] = set()
        current_id = entity_id
        while current_id not in visited:
            visited.add(current_id)
            entity = self.registry.get_entity(current_id)
            if entity is None:
                return None
            parent_event = None
            for event in self.registry.events:
                if event["acquired"] == current_id and event["acquirer"] != current_id:
                    parent_event = event
                    break
            if parent_event is None:
                return entity
            current_id = parent_event["acquirer"]
        return self.registry.get_entity(entity_id)

    def _build_chain_path(self, name: str, event: dict, root: dict) -> list[str]:
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
