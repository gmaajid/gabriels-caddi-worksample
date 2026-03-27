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
    raw = f"{name}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:6]

def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s

class MARegistry:
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

    def add_entity(self, name: str, friendly: Optional[str] = None) -> dict:
        entity_id = _generate_id(name)
        while any(e["id"] == entity_id for e in self.entities):
            entity_id = _generate_id(name + entity_id)
        entity = {"id": entity_id, "name": name, "friendly": friendly or _slugify(name)}
        self.entities.append(entity)
        self.save()
        return entity

    def add_division(self, parent_id: str, name: str, friendly: Optional[str] = None) -> dict:
        parent = self.get_entity(parent_id)
        if parent is None:
            raise ValueError(f"Parent entity '{parent_id}' not found")
        div = self.add_entity(name, friendly=friendly)
        div["parent"] = parent["id"]
        composite = f"{parent['id']}:{div['id']}"
        if "divisions" not in parent:
            parent["divisions"] = []
        parent["divisions"].append(composite)
        self.save()
        return div

    def get_entity(self, identifier: str) -> Optional[dict]:
        if ":" in identifier:
            parent_key, child_key = identifier.split(":", 1)
            parent = self.get_entity(parent_key)
            if parent is None:
                return None
            for e in self.entities:
                if e.get("parent") == parent["id"]:
                    if e["id"] == child_key or e.get("friendly") == child_key:
                        return e
            return None
        for e in self.entities:
            if e["id"] == identifier or e.get("friendly") == identifier:
                return e
        return None

    def remove_entity(self, entity_id: str) -> bool:
        entity = self.get_entity(entity_id)
        if entity is None:
            return False
        parent_id = entity.get("parent")
        if parent_id:
            parent = self.get_entity(parent_id)
            if parent and "divisions" in parent:
                composite = f"{parent['id']}:{entity['id']}"
                parent["divisions"] = [d for d in parent["divisions"] if d != composite]
        self.entities = [e for e in self.entities if e["id"] != entity["id"]]
        self.save()
        return True

    def list_entities(self) -> list[dict]:
        return list(self.entities)
