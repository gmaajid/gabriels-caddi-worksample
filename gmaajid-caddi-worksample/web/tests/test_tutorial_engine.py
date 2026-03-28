"""Tests for tutorial engine — load, step management, event generation."""

import pytest
from pathlib import Path
import yaml
from web.tutorial_engine import TutorialEngine


@pytest.fixture
def tutorials_dir(tmp_path):
    tutorial = {
        "id": "test_tutorial",
        "title": "Test Tutorial",
        "tier": 1,
        "description": "A test",
        "steps": [
            {"step": 1, "title": "Step One", "narrative": "First", "highlight_nodes": ["Apex Manufacturing"], "zoom_to": "Apex Manufacturing"},
            {"step": 2, "title": "Step Two", "narrative": "Second", "highlight_nodes": ["QuickFab"], "zoom_to": "QuickFab", "command": "caddi-cli ma list", "expected_output_contains": "acquisition"},
            {"step": 3, "title": "Step Three", "narrative": "Third", "resolution_trace": {"input": "AQF Holdings", "chain": [{"node": "AQF Holdings", "action": "start", "delay_ms": 0}, {"edge": "AQF -> Apex", "type": "ma", "weight": 1.0, "delay_ms": 800}, {"node": "Apex Manufacturing", "action": "resolved", "delay_ms": 1600}]}},
        ],
    }
    with open(tmp_path / "test_tutorial.yaml", "w") as f:
        yaml.dump(tutorial, f)
    return tmp_path


@pytest.fixture
def engine(tutorials_dir):
    return TutorialEngine(tutorials_dir)


class TestLoading:
    def test_loads_tutorials(self, engine):
        assert len(engine.list_tutorials()) == 1
        assert engine.list_tutorials()[0]["id"] == "test_tutorial"

    def test_get_tutorial(self, engine):
        t = engine.get_tutorial("test_tutorial")
        assert t["title"] == "Test Tutorial"
        assert len(t["steps"]) == 3

    def test_get_nonexistent(self, engine):
        assert engine.get_tutorial("nope") is None


class TestStepNavigation:
    def test_start(self, engine):
        step = engine.start("test_tutorial", mode="animated")
        assert step["step"] == 1
        assert step["title"] == "Step One"

    def test_next(self, engine):
        engine.start("test_tutorial", mode="animated")
        step = engine.next_step()
        assert step["step"] == 2

    def test_prev(self, engine):
        engine.start("test_tutorial", mode="animated")
        engine.next_step()
        step = engine.prev_step()
        assert step["step"] == 1

    def test_prev_at_start(self, engine):
        engine.start("test_tutorial", mode="animated")
        step = engine.prev_step()
        assert step["step"] == 1

    def test_next_at_end(self, engine):
        engine.start("test_tutorial", mode="animated")
        engine.next_step()
        engine.next_step()
        step = engine.next_step()
        assert step["step"] == 3

    def test_resolution_trace(self, engine):
        engine.start("test_tutorial", mode="animated")
        engine.next_step()
        step = engine.next_step()
        assert "resolution_trace" in step
        assert step["resolution_trace"]["input"] == "AQF Holdings"

    def test_position(self, engine):
        engine.start("test_tutorial", mode="animated")
        pos = engine.position()
        assert pos == {"current": 1, "total": 3, "tutorial_id": "test_tutorial", "mode": "animated"}
