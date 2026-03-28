"""Tutorial engine: load YAML tutorials, manage step navigation.

Tutorials are loaded once at startup from web/tutorials/*.yaml.
Each tutorial has ordered steps with narrative, graph highlights,
optional CLI commands, and optional resolution trace animations.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import yaml


class TutorialEngine:
    def __init__(self, tutorials_dir: Path):
        self._tutorials: dict[str, dict] = {}
        self._current_id: Optional[str] = None
        self._current_step: int = 0
        self._mode: str = "animated"
        self._load(tutorials_dir)

    def _load(self, tutorials_dir: Path) -> None:
        if not tutorials_dir.exists():
            return
        for path in sorted(tutorials_dir.glob("*.yaml")):
            with open(path) as f:
                data = yaml.safe_load(f)
            if data and "id" in data:
                self._tutorials[data["id"]] = data

    def list_tutorials(self) -> list[dict]:
        return [{"id": t["id"], "title": t["title"], "tier": t.get("tier", 0), "description": t.get("description", ""), "steps": len(t.get("steps", []))} for t in self._tutorials.values()]

    def get_tutorial(self, tutorial_id: str) -> Optional[dict]:
        return self._tutorials.get(tutorial_id)

    def start(self, tutorial_id: str, mode: str = "animated") -> dict:
        if tutorial_id not in self._tutorials:
            raise ValueError(f"Tutorial '{tutorial_id}' not found")
        self._current_id = tutorial_id
        self._current_step = 0
        self._mode = mode
        return self._get_current_step()

    def next_step(self) -> dict:
        if self._current_id is None:
            raise ValueError("No tutorial started")
        steps = self._tutorials[self._current_id].get("steps", [])
        if self._current_step < len(steps) - 1:
            self._current_step += 1
        return self._get_current_step()

    def prev_step(self) -> dict:
        if self._current_id is None:
            raise ValueError("No tutorial started")
        if self._current_step > 0:
            self._current_step -= 1
        return self._get_current_step()

    def position(self) -> dict:
        if self._current_id is None:
            return {"current": 0, "total": 0, "tutorial_id": None, "mode": self._mode}
        steps = self._tutorials[self._current_id].get("steps", [])
        return {"current": self._current_step + 1, "total": len(steps), "tutorial_id": self._current_id, "mode": self._mode}

    def _get_current_step(self) -> dict:
        steps = self._tutorials[self._current_id].get("steps", [])
        if not steps or self._current_step >= len(steps):
            return {}
        step = steps[self._current_step]
        return {
            "step": step.get("step", self._current_step + 1),
            "title": step.get("title", ""),
            "narrative": step.get("narrative", ""),
            "highlight_nodes": step.get("highlight_nodes", []),
            "highlight_edges": step.get("highlight_edges", []),
            "zoom_to": step.get("zoom_to"),
            "command": step.get("command"),
            "expected_output_contains": step.get("expected_output_contains"),
            "resolution_trace": step.get("resolution_trace"),
            "note": step.get("note"),
        }
