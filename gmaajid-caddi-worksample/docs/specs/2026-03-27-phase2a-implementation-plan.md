# Phase 2a: Interactive Web Application — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static web visualization with an interactive web application featuring an embedded terminal (xterm.js), real-time graph updates via WebSocket, and guided tutorials with chain traversal animations.

**Architecture:** FastAPI backend serves static files + REST API + multiplexed WebSocket (terminal PTY, graph events, tutorial commands). D3.js graph reacts to state changes from terminal commands. Two tutorial modes: animated (auto-navigate) and terminal-driven (user runs commands).

**Tech Stack:** FastAPI, uvicorn, websockets, xterm.js (vendored), D3.js v7 (vendored), Python pty module, PyYAML

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `web/server.py` | FastAPI app, REST routes, WebSocket hub, graph data builder |
| `web/pty_manager.py` | PTY process management, command detection, state change signaling |
| `web/tutorial_engine.py` | Load tutorial YAMLs, manage step state, emit events |
| `web/static/index.html` | Main page — three-panel layout |
| `web/static/css/style.css` | Layout, colors, panels, status bar |
| `web/static/css/graph.css` | Node/edge styles, animation keyframes |
| `web/static/css/terminal.css` | xterm.js theme overrides |
| `web/static/css/tutorial.css` | Tutorial panel, step cards, mode toggle |
| `web/static/js/app.js` | WebSocket connection, message routing between modules |
| `web/static/js/graph.js` | D3.js graph rendering + animation + edge weight toggle |
| `web/static/js/terminal.js` | xterm.js setup, resize, WebSocket relay |
| `web/static/js/tutorial.js` | Tutorial UI, mode toggle, step controller |
| `web/static/js/animation.js` | Chain traversal animation, diff transitions |
| `web/tutorials/01_abbreviations.yaml` | Tutorial: resolving abbreviations |
| `web/tutorials/02_typos.yaml` | Tutorial: handling typos |
| `web/tutorials/03_acquisition.yaml` | Tutorial: post-acquisition resolution |
| `web/tutorials/04_rebrand.yaml` | Tutorial: complete rebrand |
| `web/tutorials/05_broken_chains.yaml` | Tutorial: detecting broken chains |
| `web/tutorials/06_divisions.yaml` | Tutorial: divisions vs acquisitions |
| `web/tests/test_server.py` | Backend API tests |
| `web/tests/test_pty_manager.py` | PTY manager tests |
| `web/tests/test_tutorial_engine.py` | Tutorial engine tests |

### Modified Files

| File | Changes |
|------|---------|
| `pyproject.toml` | Add fastapi, uvicorn, websockets dependencies |
| `rag/cli.py` | Update `viz` command to use FastAPI instead of http.server |
| `Dockerfile` | Add vendored JS libs, update CMD |

### Removed/Replaced Files

| File | Reason |
|------|--------|
| `web/index.html` | Moves to `web/static/index.html` (restructured) |
| `web/graph.js` | Moves to `web/static/js/graph.js` (restructured) |
| `web/style.css` | Moves to `web/static/css/style.css` (restructured) |

---

## Task 1: Dependencies + Directory Structure

**Files:**
- Modify: `pyproject.toml`
- Create: `web/static/`, `web/static/css/`, `web/static/js/`, `web/static/lib/`, `web/tutorials/`, `web/tests/`

- [ ] **Step 1: Add Python dependencies to pyproject.toml**

Add to the `dependencies` list in `pyproject.toml`:

```toml
"fastapi>=0.115.0",
"uvicorn[standard]>=0.32.0",
```

- [ ] **Step 2: Install dependencies**

Run: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 3: Create directory structure and move existing files**

```bash
mkdir -p web/static/css web/static/js web/static/lib web/tutorials web/tests
touch web/__init__.py web/tests/__init__.py
# Move existing files to new structure
mv web/index.html web/static/index.html
mv web/graph.js web/static/js/graph.js
mv web/style.css web/static/css/style.css
```

- [ ] **Step 4: Download and vendor xterm.js**

```bash
# Download xterm.js and addons
curl -sL https://cdn.jsdelivr.net/npm/xterm@5.5.0/lib/xterm.min.js -o web/static/lib/xterm.min.js
curl -sL https://cdn.jsdelivr.net/npm/xterm@5.5.0/css/xterm.css -o web/static/lib/xterm.css
curl -sL https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.min.js -o web/static/lib/xterm-addon-fit.min.js
curl -sL https://cdn.jsdelivr.net/npm/@xterm/addon-web-links@0.11.0/lib/addon-web-links.min.js -o web/static/lib/xterm-addon-web-links.min.js
# Vendor D3 (replace CDN reference)
curl -sL https://d3js.org/d3.v7.min.js -o web/static/lib/d3.v7.min.js
```

- [ ] **Step 5: Verify existing tests still pass**

Run: `.venv/bin/pytest --tb=short -q`
Expected: 175 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml web/
git commit -m "chore: restructure web/ for Phase 2a, add FastAPI deps, vendor JS libs"
```

---

## Task 2: PTY Manager

**Files:**
- Create: `web/pty_manager.py`
- Create: `web/tests/test_pty_manager.py`

- [ ] **Step 1: Write failing tests**

Create `web/tests/test_pty_manager.py`:

```python
"""Tests for PTY manager — process lifecycle and command detection."""

import asyncio
import pytest
from web.pty_manager import PTYManager


class TestPTYLifecycle:
    def test_spawn_and_close(self):
        mgr = PTYManager()
        mgr.spawn()
        assert mgr.is_alive()
        mgr.close()
        assert not mgr.is_alive()

    def test_write_and_read(self):
        mgr = PTYManager()
        mgr.spawn()
        mgr.write(b"echo hello\r")
        import time
        time.sleep(0.5)
        output = mgr.read_available()
        mgr.close()
        assert b"hello" in output

    def test_resize(self):
        mgr = PTYManager()
        mgr.spawn()
        # Should not raise
        mgr.resize(120, 40)
        mgr.close()


class TestCommandDetection:
    def test_detects_caddi_cli_command(self):
        mgr = PTYManager()
        assert mgr.is_state_changing_command("caddi-cli ma add --entity-only --name Foo")
        assert mgr.is_state_changing_command("./caddi-cli ma remove abc123")
        assert mgr.is_state_changing_command("caddi-cli ingest")
        assert mgr.is_state_changing_command("caddi-cli demo generate")

    def test_non_state_changing_commands(self):
        mgr = PTYManager()
        assert not mgr.is_state_changing_command("caddi-cli ma list")
        assert not mgr.is_state_changing_command("caddi-cli mappings")
        assert not mgr.is_state_changing_command("caddi-cli --help")
        assert not mgr.is_state_changing_command("ls -la")
        assert not mgr.is_state_changing_command("echo hello")

    def test_prompt_detection(self):
        mgr = PTYManager()
        assert mgr.detect_prompt("caddi> ")
        assert mgr.detect_prompt("caddi> \r\n")
        assert not mgr.detect_prompt("still running...")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest web/tests/test_pty_manager.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement PTYManager**

Create `web/pty_manager.py`:

```python
"""PTY manager: spawn and manage a pseudo-terminal for the web terminal.

Provides non-blocking read/write to a bash shell with venv activated.
Detects when caddi-cli state-changing commands complete to trigger
graph refreshes.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import signal
import struct
import termios
from pathlib import Path
from typing import Optional


# Commands that change M&A registry, RAG, or demo data
STATE_CHANGING_PATTERNS = [
    r"caddi-cli\s+ma\s+(add|remove)",
    r"\./caddi-cli\s+ma\s+(add|remove)",
    r"caddi-cli\s+ingest",
    r"\./caddi-cli\s+ingest",
    r"caddi-cli\s+demo\s+generate",
    r"\./caddi-cli\s+demo\s+generate",
    r"caddi-cli\s+revert",
    r"\./caddi-cli\s+revert",
]

PROMPT_MARKER = "caddi> "


class PTYManager:
    """Manages a pseudo-terminal running a bash shell."""

    def __init__(
        self,
        working_dir: Optional[str] = None,
        venv_path: Optional[str] = None,
    ):
        self.working_dir = working_dir or str(Path(__file__).resolve().parent.parent)
        self.venv_path = venv_path or str(
            Path(self.working_dir) / ".venv"
        )
        self._master_fd: Optional[int] = None
        self._pid: Optional[int] = None
        self._current_command: str = ""
        self._output_buffer: bytes = b""

    def spawn(self) -> None:
        """Fork a PTY process with bash and venv activated."""
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = self.venv_path
        env["PATH"] = f"{self.venv_path}/bin:{env.get('PATH', '')}"
        env["TERM"] = "xterm-256color"
        env["PS1"] = PROMPT_MARKER
        env["CADDI_CLI_NAME"] = "caddi-cli"

        pid, fd = pty.openpty()
        child_pid = os.fork()

        if child_pid == 0:
            # Child process
            os.close(fd)
            os.setsid()
            # Set controlling terminal
            slave_fd = os.open(os.ttyname(pid), os.O_RDWR)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.close(pid)
            os.chdir(self.working_dir)
            os.execvpe(
                "/bin/bash",
                ["/bin/bash", "--norc", "--noprofile"],
                env,
            )
        else:
            # Parent process
            os.close(pid)
            self._master_fd = fd
            self._pid = child_pid
            # Set non-blocking
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def is_alive(self) -> bool:
        """Check if the PTY process is still running."""
        if self._pid is None:
            return False
        try:
            pid, status = os.waitpid(self._pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def close(self) -> None:
        """Terminate the PTY process."""
        if self._master_fd is not None:
            os.close(self._master_fd)
            self._master_fd = None
        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGTERM)
                os.waitpid(self._pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
            self._pid = None

    def write(self, data: bytes) -> None:
        """Write data to the PTY (keystrokes from browser)."""
        if self._master_fd is not None:
            os.write(self._master_fd, data)
            # Track command being typed
            try:
                text = data.decode("utf-8", errors="ignore")
                if "\r" in text or "\n" in text:
                    self._current_command = self._output_buffer.decode(
                        "utf-8", errors="ignore"
                    ).split("\n")[-1].strip()
            except Exception:
                pass

    def read_available(self) -> bytes:
        """Read all available output from the PTY (non-blocking)."""
        if self._master_fd is None:
            return b""
        chunks = []
        while True:
            try:
                chunk = os.read(self._master_fd, 4096)
                if not chunk:
                    break
                chunks.append(chunk)
                self._output_buffer += chunk
                # Keep buffer manageable
                if len(self._output_buffer) > 65536:
                    self._output_buffer = self._output_buffer[-32768:]
            except OSError:
                break
        return b"".join(chunks)

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window."""
        if self._master_fd is not None:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def is_state_changing_command(self, command: str) -> bool:
        """Check if a command would change M&A registry or RAG state."""
        for pattern in STATE_CHANGING_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def detect_prompt(self, output: str) -> bool:
        """Detect if the output contains the shell prompt (command finished)."""
        return PROMPT_MARKER in output
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest web/tests/test_pty_manager.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add web/pty_manager.py web/tests/test_pty_manager.py
git commit -m "feat: PTY manager with command detection and state change signaling"
```

---

## Task 3: Tutorial Engine

**Files:**
- Create: `web/tutorial_engine.py`
- Create: `web/tests/test_tutorial_engine.py`
- Create: `web/tutorials/01_abbreviations.yaml` through `06_divisions.yaml`

- [ ] **Step 1: Write failing tests**

Create `web/tests/test_tutorial_engine.py`:

```python
"""Tests for tutorial engine — load, step management, event generation."""

import pytest
from pathlib import Path
import yaml

from web.tutorial_engine import TutorialEngine, TutorialStep


@pytest.fixture
def tutorials_dir(tmp_path):
    """Create a temp tutorials directory with one tutorial."""
    tutorial = {
        "id": "test_tutorial",
        "title": "Test Tutorial",
        "tier": 1,
        "description": "A test tutorial",
        "steps": [
            {
                "step": 1,
                "title": "Step One",
                "narrative": "First step",
                "highlight_nodes": ["Apex Manufacturing"],
                "zoom_to": "Apex Manufacturing",
                "command": None,
            },
            {
                "step": 2,
                "title": "Step Two",
                "narrative": "Second step",
                "highlight_nodes": ["QuickFab Industries"],
                "zoom_to": "QuickFab Industries",
                "command": "caddi-cli ma list",
                "expected_output_contains": "acquisition",
            },
            {
                "step": 3,
                "title": "Step Three",
                "narrative": "Third step with animation",
                "resolution_trace": {
                    "input": "AQF Holdings",
                    "chain": [
                        {"node": "AQF Holdings", "action": "start", "delay_ms": 0},
                        {"edge": "AQF Holdings -> Apex", "type": "ma", "weight": 1.0, "delay_ms": 800},
                        {"node": "Apex Manufacturing", "action": "resolved", "delay_ms": 1600},
                    ],
                },
            },
        ],
    }
    path = tmp_path / "test_tutorial.yaml"
    with open(path, "w") as f:
        yaml.dump(tutorial, f)
    return tmp_path


@pytest.fixture
def engine(tutorials_dir):
    return TutorialEngine(tutorials_dir)


class TestTutorialLoading:
    def test_loads_tutorials(self, engine):
        tutorials = engine.list_tutorials()
        assert len(tutorials) == 1
        assert tutorials[0]["id"] == "test_tutorial"

    def test_get_tutorial(self, engine):
        t = engine.get_tutorial("test_tutorial")
        assert t is not None
        assert t["title"] == "Test Tutorial"
        assert len(t["steps"]) == 3

    def test_get_nonexistent_tutorial(self, engine):
        assert engine.get_tutorial("nonexistent") is None


class TestStepManagement:
    def test_start_tutorial(self, engine):
        step = engine.start("test_tutorial", mode="animated")
        assert step["step"] == 1
        assert step["title"] == "Step One"

    def test_next_step(self, engine):
        engine.start("test_tutorial", mode="animated")
        step = engine.next_step()
        assert step["step"] == 2

    def test_prev_step(self, engine):
        engine.start("test_tutorial", mode="animated")
        engine.next_step()
        step = engine.prev_step()
        assert step["step"] == 1

    def test_prev_at_start_stays(self, engine):
        engine.start("test_tutorial", mode="animated")
        step = engine.prev_step()
        assert step["step"] == 1

    def test_next_at_end_stays(self, engine):
        engine.start("test_tutorial", mode="animated")
        engine.next_step()
        engine.next_step()
        step = engine.next_step()
        assert step["step"] == 3  # stays at last

    def test_step_has_resolution_trace(self, engine):
        engine.start("test_tutorial", mode="animated")
        engine.next_step()
        step = engine.next_step()  # step 3
        assert "resolution_trace" in step
        assert step["resolution_trace"]["input"] == "AQF Holdings"

    def test_current_position(self, engine):
        engine.start("test_tutorial", mode="animated")
        pos = engine.position()
        assert pos == {"current": 1, "total": 3, "tutorial_id": "test_tutorial", "mode": "animated"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest web/tests/test_tutorial_engine.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement TutorialEngine**

Create `web/tutorial_engine.py`:

```python
"""Tutorial engine: load YAML tutorials, manage step navigation, emit events.

Tutorials are loaded once at startup from web/tutorials/*.yaml.
Each tutorial has an ordered list of steps with narrative text,
graph highlight instructions, optional CLI commands, and optional
resolution trace animations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class TutorialStep:
    """A single step in a tutorial."""
    step: int
    title: str
    narrative: str
    highlight_nodes: list[str]
    highlight_edges: list[str]
    zoom_to: Optional[str]
    command: Optional[str]
    expected_output_contains: Optional[str]
    resolution_trace: Optional[dict]
    note: Optional[str]


class TutorialEngine:
    """Manages tutorial state and step navigation."""

    def __init__(self, tutorials_dir: Path):
        self._tutorials: dict[str, dict] = {}
        self._current_id: Optional[str] = None
        self._current_step: int = 0
        self._mode: str = "animated"
        self._load(tutorials_dir)

    def _load(self, tutorials_dir: Path) -> None:
        """Load all YAML tutorial files from directory."""
        if not tutorials_dir.exists():
            return
        for path in sorted(tutorials_dir.glob("*.yaml")):
            with open(path) as f:
                data = yaml.safe_load(f)
            if data and "id" in data:
                self._tutorials[data["id"]] = data

    def list_tutorials(self) -> list[dict]:
        """Return summary of all tutorials."""
        return [
            {
                "id": t["id"],
                "title": t["title"],
                "tier": t.get("tier", 0),
                "description": t.get("description", ""),
                "steps": len(t.get("steps", [])),
            }
            for t in self._tutorials.values()
        ]

    def get_tutorial(self, tutorial_id: str) -> Optional[dict]:
        """Get full tutorial definition by ID."""
        return self._tutorials.get(tutorial_id)

    def start(self, tutorial_id: str, mode: str = "animated") -> dict:
        """Start a tutorial, return the first step."""
        if tutorial_id not in self._tutorials:
            raise ValueError(f"Tutorial '{tutorial_id}' not found")
        self._current_id = tutorial_id
        self._current_step = 0
        self._mode = mode
        return self._get_current_step()

    def next_step(self) -> dict:
        """Advance to the next step, return it."""
        if self._current_id is None:
            raise ValueError("No tutorial started")
        steps = self._tutorials[self._current_id].get("steps", [])
        if self._current_step < len(steps) - 1:
            self._current_step += 1
        return self._get_current_step()

    def prev_step(self) -> dict:
        """Go back one step, return it."""
        if self._current_id is None:
            raise ValueError("No tutorial started")
        if self._current_step > 0:
            self._current_step -= 1
        return self._get_current_step()

    def position(self) -> dict:
        """Return current position in the tutorial."""
        if self._current_id is None:
            return {"current": 0, "total": 0, "tutorial_id": None, "mode": self._mode}
        steps = self._tutorials[self._current_id].get("steps", [])
        return {
            "current": self._current_step + 1,
            "total": len(steps),
            "tutorial_id": self._current_id,
            "mode": self._mode,
        }

    def _get_current_step(self) -> dict:
        """Return the current step data."""
        steps = self._tutorials[self._current_id].get("steps", [])
        if not steps or self._current_step >= len(steps):
            return {}
        step = steps[self._current_step]
        # Normalize fields with defaults
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest web/tests/test_tutorial_engine.py -v`
Expected: All PASS

- [ ] **Step 5: Create the 6 tutorial YAML files**

Create `web/tutorials/01_abbreviations.yaml`:

```yaml
id: "01_abbreviations"
title: "Resolving Abbreviations"
tier: 1
description: "See how 'APEX MFG' automatically maps to 'Apex Manufacturing' using token-level similarity with abbreviation expansion."
steps:
  - step: 1
    title: "The Problem"
    narrative: "The same supplier appears with different name variants across purchase orders. 'APEX MFG', 'Apex Mfg', and 'Apex Manufacturing Inc' are all the same company."
    highlight_nodes: ["Apex Manufacturing"]
    zoom_to: "Apex Manufacturing"

  - step: 2
    title: "Abbreviation Expansion"
    narrative: "The system expands 'MFG' to 'Manufacturing', strips legal suffixes like 'Inc', and normalizes case. This produces identical token sets."
    highlight_nodes: ["APEX MFG", "Apex Mfg", "Apex Manufacturing Inc", "APEX Manufacturing Inc"]
    zoom_to: "Apex Manufacturing"
    command: "caddi-cli mappings"

  - step: 3
    title: "Confidence Score"
    narrative: "Each variant has a confidence score showing how well it matches the canonical name. J=Jaccard (token overlap), E=Embedding (semantic similarity), C=Combined."
    highlight_nodes: ["Apex Manufacturing"]
    zoom_to: "Apex Manufacturing"
    note: "Toggle 'Show Edge Weights' in the sidebar to see scores on all edges."

  - step: 4
    title: "Try It Yourself"
    narrative: "Run the benchmark to see how Tier 1 scenarios perform. All abbreviation and case variants resolve with 100% accuracy."
    command: "caddi-cli demo run --extended"
```

Create `web/tutorials/02_typos.yaml`:

```yaml
id: "02_typos"
title: "Handling Typos"
tier: 2
description: "Watch the system resolve misspelled supplier names using fuzzy token matching."
steps:
  - step: 1
    title: "Typos in Real Data"
    narrative: "Data entry errors are common. 'Stellr Metalworks' (missing letter), 'Titan Forge LLC' (extra space), and 'QuickFab Industires' (transposed letters) all need to resolve correctly."
    highlight_nodes: ["Stellar Metalworks", "TitanForge LLC", "QuickFab Industries"]

  - step: 2
    title: "Fuzzy Token Matching"
    narrative: "The anchor resolver uses Levenshtein edit distance to match tokens with small differences. 'Stellr' matches 'Stellar' with 85% similarity (1 edit in 7 characters)."
    highlight_nodes: ["Stellar Metalworks"]
    zoom_to: "Stellar Metalworks"

  - step: 3
    title: "Benchmark Results"
    narrative: "Tier 2 scenarios achieve 89% F1. The remaining 11% are heavily corrupted names (OCR digit substitution, multiple compounded errors) that correctly go to human review."
    command: "caddi-cli demo run --extended"
```

Create `web/tutorials/03_acquisition.yaml`:

```yaml
id: "03_acquisition"
title: "Post-Acquisition Resolution"
tier: 3
description: "How the system resolves names after Apex acquired QuickFab in July 2024."
steps:
  - step: 1
    title: "The Acquisition"
    narrative: "In July 2024, Apex Manufacturing acquired QuickFab Industries. After the acquisition, orders started appearing under new names like 'Apex-QuickFab Industries' and 'AQF Holdings'."
    highlight_nodes: ["Apex Manufacturing", "QuickFab Industries"]
    zoom_to: "Apex Manufacturing"

  - step: 2
    title: "The M&A Registry"
    narrative: "The M&A registry records corporate events with dates. Let's look at this acquisition."
    highlight_nodes: ["Apex Manufacturing"]
    zoom_to: "Apex Manufacturing"
    command: "caddi-cli ma list"

  - step: 3
    title: "Chain Traversal"
    narrative: "Watch how 'AQF Holdings' resolves back to 'Apex Manufacturing' through the M&A chain."
    resolution_trace:
      input: "AQF Holdings"
      chain:
        - node: "AQF Holdings"
          action: "start"
          delay_ms: 0
        - edge: "AQF Holdings -> Apex Manufacturing"
          type: "ma"
          weight: 1.0
          delay_ms: 800
        - node: "Apex Manufacturing"
          action: "resolved"
          delay_ms: 1600
    highlight_nodes: ["AQF Holdings", "Apex Manufacturing"]
    zoom_to: "AQF Holdings"

  - step: 4
    title: "Date Awareness"
    narrative: "The resolver is date-aware. An order for 'AQF Holdings' dated before July 2024 would NOT resolve — that name didn't exist yet. This prevents temporal conflicts."
    highlight_nodes: ["AQF Holdings"]
    zoom_to: "AQF Holdings"
```

Create `web/tutorials/04_rebrand.yaml`:

```yaml
id: "04_rebrand"
title: "Complete Rebrand (Zero Overlap)"
tier: 4
description: "'Zenith Thermal Solutions' has ZERO token overlap with 'Precision Thermal Co'. No AI clustering can solve this. Only the M&A registry knows they're the same company."
steps:
  - step: 1
    title: "The Challenge"
    narrative: "Precision Thermal Co rebranded to 'Zenith Thermal Solutions' in January 2025. The new name shares zero tokens with the original. Clustering scores: J=0.00, E=0.15."
    highlight_nodes: ["Precision Thermal Co"]
    zoom_to: "Precision Thermal Co"

  - step: 2
    title: "M&A Registry to the Rescue"
    narrative: "The M&A registry records this rebrand event. The resolver matches 'Zenith Thermal Solutions' against the registry's resulting_names and follows the chain back."
    resolution_trace:
      input: "Zenith Thermal Solutions"
      chain:
        - node: "Zenith Thermal Solutions"
          action: "start"
          delay_ms: 0
        - edge: "Zenith Thermal Solutions -> Precision Thermal Co"
          type: "ma"
          weight: 1.0
          delay_ms: 800
        - node: "Precision Thermal Co"
          action: "resolved"
          delay_ms: 1600
    highlight_nodes: ["Zenith Thermal Solutions", "Precision Thermal Co"]
    zoom_to: "Zenith Thermal Solutions"

  - step: 3
    title: "The Transparency Principle"
    narrative: "This is Tier 4 (Adversarial). Without the M&A registry entry, recall is 0%. The system is transparent about what it can and cannot solve — Tier 4 scores tell you exactly where your registry has gaps."
    command: "caddi-cli demo run --extended"
```

Create `web/tutorials/05_broken_chains.yaml`:

```yaml
id: "05_broken_chains"
title: "Detecting Broken Chains"
tier: 0
description: "What happens when M&A data is incomplete? The system detects gaps and alerts you."
steps:
  - step: 1
    title: "Current State"
    narrative: "Right now the M&A registry is healthy — no validation issues."
    command: "caddi-cli ma validate"

  - step: 2
    title: "Simulate a Gap"
    narrative: "In terminal-driven mode, remove the QuickFab acquisition event. In animated mode, we'll show what the result would look like."
    note: "Terminal-driven: run 'caddi-cli ma list' to find the acquisition event ID, then 'caddi-cli ma remove <id> --force'"

  - step: 3
    title: "The Broken Chain"
    narrative: "Without the acquisition event, 'AQF Holdings' becomes unresolved. The system flags this as a broken chain — it can see that 'AQF Holdings' exists in the data but has no path to any canonical entity."

  - step: 4
    title: "Recovery"
    narrative: "Add the event back to restore the chain. The system re-validates and the alert clears."
    note: "Terminal-driven: run 'caddi-cli ma add --type acquisition --date 2024-07-15 --acquirer \"Apex Manufacturing\" --acquired \"QuickFab Industries\" --resulting-name \"AQF Holdings\"'"
```

Create `web/tutorials/06_divisions.yaml`:

```yaml
id: "06_divisions"
title: "Divisions vs Acquisitions"
tier: 0
description: "Bright Star Foundrys is a division of Apex — it keeps its own identity for POs but the parent relationship is tracked."
steps:
  - step: 1
    title: "Division Structure"
    narrative: "Apex Manufacturing has three divisions: Bright Star Foundrys, Juniper Racing Parts, and Knight Fastener Fabrication Services. Each is operationally independent."
    highlight_nodes: ["Bright Star Foundrys", "Juniper Racing Parts", "Knight Fastener Fabrication Services", "Apex Manufacturing"]
    zoom_to: "Apex Manufacturing"

  - step: 2
    title: "Independent Identity"
    narrative: "POs from 'Bright Star Foundrys' resolve to 'Bright Star Foundrys', NOT 'Apex Manufacturing'. The division keeps its own canonical name for procurement tracking."
    highlight_nodes: ["Bright Star Foundrys"]
    zoom_to: "Bright Star Foundrys"

  - step: 3
    title: "Parent Relationship"
    narrative: "The purple edge connects divisions to their parent. This enables aggregate analytics — 'total Apex family spend' includes all divisions."
    highlight_edges: ["division"]
    zoom_to: "Apex Manufacturing"
    command: "caddi-cli ma list"
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/pytest --tb=short -q`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add web/tutorial_engine.py web/tests/test_tutorial_engine.py web/tutorials/
git commit -m "feat: tutorial engine with 6 guided tutorials and step navigation"
```

---

## Task 4: FastAPI Server

**Files:**
- Create: `web/server.py`
- Create: `web/tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Create `web/tests/test_server.py`:

```python
"""Tests for FastAPI server — REST API and WebSocket."""

import pytest
from fastapi.testclient import TestClient

from web.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestRESTAPI:
    def test_graph_endpoint(self, client):
        response = client.get("/api/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert "alerts" in data

    def test_tutorials_list(self, client):
        response = client.get("/api/tutorials")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_tutorial_by_id(self, client):
        # Get list first
        response = client.get("/api/tutorials")
        tutorials = response.json()
        if tutorials:
            tid = tutorials[0]["id"]
            response = client.get(f"/api/tutorials/{tid}")
            assert response.status_code == 200
            assert response.json()["id"] == tid

    def test_tutorial_not_found(self, client):
        response = client.get("/api/tutorials/nonexistent")
        assert response.status_code == 404

    def test_static_index(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "CADDi" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest web/tests/test_server.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement FastAPI server**

Create `web/server.py`:

```python
"""FastAPI server for the CADDi web application.

Serves static files, REST API for graph data and tutorials,
and a multiplexed WebSocket for terminal I/O, graph updates,
and tutorial events.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from web.pty_manager import PTYManager
from web.tutorial_engine import TutorialEngine

# Paths
WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TUTORIALS_DIR = WEB_DIR / "tutorials"
PROJECT_ROOT = WEB_DIR.parent

# Shared state (single-user for Phase 2a)
_pty: Optional[PTYManager] = None
_tutorial_engine: Optional[TutorialEngine] = None
_graph_data: Optional[dict] = None
_connected_clients: list[WebSocket] = []


def _build_graph_data() -> dict:
    """Build graph data from current project state.

    Imports from the project's modules to build node/edge data.
    This is called on startup and after state-changing commands.
    """
    import sys
    # Ensure project root is in path for imports
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from rag.cli import _build_viz_data
    return _build_viz_data()


def _compute_diff(old: dict, new: dict) -> dict:
    """Compute the diff between two graph states."""
    old_node_ids = {n["id"] for n in (old or {}).get("nodes", [])}
    new_node_ids = {n["id"] for n in new.get("nodes", [])}
    old_edge_keys = {
        f"{e.get('source', '')}->{e.get('target', '')}"
        for e in (old or {}).get("edges", [])
    }
    new_edge_keys = {
        f"{e.get('source', '')}->{e.get('target', '')}"
        for e in new.get("edges", [])
    }
    return {
        "added_nodes": list(new_node_ids - old_node_ids),
        "removed_nodes": list(old_node_ids - new_node_ids),
        "added_edges": list(new_edge_keys - old_edge_keys),
        "removed_edges": list(old_edge_keys - new_edge_keys),
    }


async def _broadcast(channel: str, msg_type: str, data: dict) -> None:
    """Send a message to all connected WebSocket clients."""
    message = json.dumps({"channel": channel, "type": msg_type, "data": data})
    disconnected = []
    for ws in _connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _connected_clients.remove(ws)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _pty, _tutorial_engine, _graph_data
        # Startup
        _tutorial_engine = TutorialEngine(TUTORIALS_DIR)
        _graph_data = _build_graph_data()
        yield
        # Shutdown
        if _pty:
            _pty.close()

    app = FastAPI(title="CADDi Entity Resolution", lifespan=lifespan)

    # --- Static files ---
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    # --- REST API ---

    @app.get("/api/graph")
    async def get_graph():
        return _graph_data or {"nodes": [], "edges": [], "alerts": []}

    @app.get("/api/tutorials")
    async def list_tutorials():
        if _tutorial_engine:
            return _tutorial_engine.list_tutorials()
        return []

    @app.get("/api/tutorials/{tutorial_id}")
    async def get_tutorial(tutorial_id: str):
        if _tutorial_engine:
            t = _tutorial_engine.get_tutorial(tutorial_id)
            if t:
                return t
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Tutorial not found"})

    # --- WebSocket ---

    @app.websocket("/ws")
    async def websocket_handler(websocket: WebSocket):
        global _pty, _graph_data

        await websocket.accept()
        _connected_clients.append(websocket)

        # Spawn PTY if not running
        if _pty is None or not _pty.is_alive():
            _pty = PTYManager(working_dir=str(PROJECT_ROOT))
            _pty.spawn()

        # Start PTY read loop
        async def pty_reader():
            """Read PTY output and relay to client."""
            while True:
                try:
                    output = _pty.read_available()
                    if output:
                        await websocket.send_text(json.dumps({
                            "channel": "terminal",
                            "type": "terminal-output",
                            "data": {"data": output.decode("utf-8", errors="replace")},
                        }))
                        # Check if a state-changing command completed
                        output_str = output.decode("utf-8", errors="replace")
                        if _pty.detect_prompt(output_str):
                            # Check if the last command was state-changing
                            cmd = _pty._current_command
                            if cmd and _pty.is_state_changing_command(cmd):
                                old_graph = _graph_data
                                _graph_data = _build_graph_data()
                                diff = _compute_diff(old_graph, _graph_data)
                                graph_update = dict(_graph_data)
                                graph_update["diff"] = diff
                                await _broadcast("graph", "graph-updated", graph_update)
                                _pty._current_command = ""
                    await asyncio.sleep(0.05)
                except Exception:
                    break

        reader_task = asyncio.create_task(pty_reader())

        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                channel = msg.get("channel", "")
                msg_type = msg.get("type", "")
                data = msg.get("data", {})

                if channel == "terminal":
                    if msg_type == "terminal-input":
                        _pty.write(data.get("data", "").encode("utf-8"))
                    elif msg_type == "terminal-resize":
                        _pty.resize(data.get("cols", 80), data.get("rows", 24))

                elif channel == "graph":
                    if msg_type == "graph-request":
                        _graph_data = _build_graph_data()
                        await websocket.send_text(json.dumps({
                            "channel": "graph",
                            "type": "graph-updated",
                            "data": _graph_data,
                        }))

                elif channel == "tutorial":
                    if msg_type == "tutorial-start":
                        step = _tutorial_engine.start(
                            data["id"], mode=data.get("mode", "animated")
                        )
                        await websocket.send_text(json.dumps({
                            "channel": "tutorial",
                            "type": "tutorial-step",
                            "data": step,
                        }))
                    elif msg_type == "tutorial-next":
                        step = _tutorial_engine.next_step()
                        await websocket.send_text(json.dumps({
                            "channel": "tutorial",
                            "type": "tutorial-step",
                            "data": step,
                        }))
                    elif msg_type == "tutorial-prev":
                        step = _tutorial_engine.prev_step()
                        await websocket.send_text(json.dumps({
                            "channel": "tutorial",
                            "type": "tutorial-step",
                            "data": step,
                        }))

        except WebSocketDisconnect:
            pass
        finally:
            reader_task.cancel()
            if websocket in _connected_clients:
                _connected_clients.remove(websocket)

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest web/tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add web/server.py web/tests/test_server.py
git commit -m "feat: FastAPI server with REST API, WebSocket hub, and PTY relay"
```

---

## Task 5: Frontend — HTML Layout + CSS

**Files:**
- Rewrite: `web/static/index.html`
- Create: `web/static/css/style.css`, `graph.css`, `terminal.css`, `tutorial.css`

- [ ] **Step 1: Rewrite index.html with three-panel layout**

Rewrite `web/static/index.html` with the new layout: topbar, sidebar, main content (graph/tutorials tabs), terminal panel (bottom, resizable), status bar. Reference vendored libs from `/static/lib/`, CSS from `/static/css/`, JS from `/static/js/`.

Key structure:
```html
<link rel="stylesheet" href="/static/lib/xterm.css">
<link rel="stylesheet" href="/static/css/style.css">
<link rel="stylesheet" href="/static/css/graph.css">
<link rel="stylesheet" href="/static/css/terminal.css">
<link rel="stylesheet" href="/static/css/tutorial.css">
...
<div id="terminal-panel"><div id="terminal"></div></div>
<div id="resize-handle"></div>
...
<script src="/static/lib/d3.v7.min.js"></script>
<script src="/static/lib/xterm.min.js"></script>
<script src="/static/lib/xterm-addon-fit.min.js"></script>
<script type="module" src="/static/js/app.js"></script>
```

- [ ] **Step 2: Create CSS files**

Split the existing `style.css` into 4 focused files:
- `style.css` — layout grid, colors, sidebar, status bar, panels, resize handle
- `graph.css` — node/edge styles, animation keyframes (trace-start, trace-active, trace-resolved), edge weight labels
- `terminal.css` — xterm.js theme overrides matching the dark UI
- `tutorial.css` — tutorial cards, step navigation, mode toggle, narrative panel

- [ ] **Step 3: Verify static files serve correctly**

Run the server temporarily and check the browser loads:
```bash
.venv/bin/python -c "from web.server import create_app; import uvicorn; uvicorn.run(create_app(), host='0.0.0.0', port=8181)" &
sleep 5
curl -s http://localhost:8181/ | head -5
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add web/static/
git commit -m "feat: three-panel layout with resizable terminal, sidebar, status bar"
```

---

## Task 6: Frontend — JavaScript Modules

**Files:**
- Create: `web/static/js/app.js`
- Rewrite: `web/static/js/graph.js`
- Create: `web/static/js/terminal.js`
- Create: `web/static/js/tutorial.js`
- Create: `web/static/js/animation.js`

- [ ] **Step 1: Create app.js — WebSocket connection + message router**

```javascript
// web/static/js/app.js — WebSocket hub + message routing
// Connects to /ws, routes messages to graph/terminal/tutorial modules

export class App {
    constructor() {
        this.ws = null;
        this.handlers = { terminal: [], graph: [], tutorial: [] };
        this.statusEl = document.getElementById('status-text');
    }

    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${location.host}/ws`);
        this.ws.onopen = () => this.updateStatus('connected');
        this.ws.onclose = () => this.updateStatus('disconnected');
        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            const handlers = this.handlers[msg.channel] || [];
            handlers.forEach(h => h(msg.type, msg.data));
        };
    }

    send(channel, type, data = {}) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ channel, type, data }));
        }
    }

    on(channel, handler) {
        this.handlers[channel] = this.handlers[channel] || [];
        this.handlers[channel].push(handler);
    }

    updateStatus(status) {
        if (this.statusEl) this.statusEl.textContent = status;
    }
}
```

- [ ] **Step 2: Create terminal.js — xterm.js setup**

Sets up xterm.js Terminal, connects to WebSocket terminal channel, handles resize via FitAddon.

- [ ] **Step 3: Rewrite graph.js — D3.js with animation support + edge weight toggle**

Port existing graph.js to work with the WebSocket-driven updates instead of fetch. Add:
- `updateGraph(data)` method that animates diffs (fade in/out nodes and edges)
- Edge weight labels (togglable via checkbox, persisted to localStorage)
- `highlightNodes(nodeIds)` / `clearHighlights()` for tutorial integration
- `zoomToNode(nodeId)` — smooth pan/zoom transition
- `playTrace(chain)` — chain traversal animation with configurable delays

- [ ] **Step 4: Create tutorial.js — Tutorial UI + mode toggle**

Handles tutorial list rendering, step display, mode toggle (animated/terminal-driven), command display/copy, and communication with app.js for graph control.

- [ ] **Step 5: Create animation.js — Chain traversal + diff transitions**

Dedicated animation module:
- `playChainTrace(chain, graphModule)` — animate resolution chain step by step
- `animateDiff(diff, graphModule)` — animate graph updates (new nodes fade in, removed fade out)
- `showDiffBanner(diff)` — transient "+2 nodes, -1 node" banner

- [ ] **Step 6: Verify end-to-end locally**

```bash
# Start server
.venv/bin/python -c "from web.server import create_app; import uvicorn; uvicorn.run(create_app(), host='0.0.0.0', port=8181)"
# Open browser to http://localhost:8181
# Verify: graph loads, terminal works, tutorials display
```

- [ ] **Step 7: Commit**

```bash
git add web/static/js/
git commit -m "feat: JS modules — WebSocket app, terminal, graph with animations, tutorials"
```

---

## Task 7: Update CLI viz Command

**Files:**
- Modify: `rag/cli.py`

- [ ] **Step 1: Replace http.server with FastAPI/uvicorn in viz command**

Find the `viz` function in `rag/cli.py` and replace the implementation:

```python
@cli.command()
@click.option("--port", default=8080, help="Port for the web server")
@click.option("--no-browser", is_flag=True, help="Don't auto-open browser")
def viz(port, no_browser):
    """Launch the interactive web application.

    Starts the FastAPI server with embedded terminal, interactive
    graph visualization, and guided tutorials.

    Example:
        caddi-cli viz
        caddi-cli viz --port 9090
        caddi-cli viz --no-browser
    """
    import threading
    import webbrowser

    from web.server import create_app
    import uvicorn

    console.print(f"[green]Starting CADDi web application on port {port}...[/green]")
    console.print(f"\n  Open: [bold cyan]http://localhost:{port}[/bold cyan]")
    console.print("  Press Ctrl+C to stop.\n")

    if not no_browser:
        threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="warning")
```

Remove the old `_build_viz_data()` helper function — it stays in `rag/cli.py` but is now called by `web/server.py`.

- [ ] **Step 2: Verify the command works**

```bash
./caddi-cli viz --help
# Should show the updated help text
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add rag/cli.py
git commit -m "feat: caddi-cli viz now launches FastAPI app with terminal + tutorials"
```

---

## Task 8: Update Dockerfile

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Update Dockerfile for Phase 2a**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml caddi-cli ./
COPY rag/ rag/
COPY src/ src/
COPY config/ config/
COPY data/ data/
COPY web/ web/
COPY docs/ docs/

# Make caddi-cli executable
RUN chmod +x caddi-cli

# Install dependencies (includes fastapi, uvicorn)
RUN pip install --no-cache-dir -e ".[dev]"

# Pre-download the embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8080

ENTRYPOINT ["./caddi-cli"]
CMD ["viz", "--no-browser"]
```

Note: default CMD is now `viz --no-browser` (starts the web app, doesn't try to open a browser in the container).

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "docker: update for Phase 2a — default to viz server, include web assets"
```

---

## Task 9: Integration Test + Push

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/pytest --tb=short -q
```
Expected: All tests pass (175 existing + ~20 new = ~195 total)

- [ ] **Step 2: End-to-end manual test**

```bash
./caddi-cli viz --port 8181 --no-browser &
sleep 10
# Test REST API
curl -s http://localhost:8181/api/graph | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Nodes: {len(d[\"nodes\"])}, Edges: {len(d[\"edges\"])}')"
curl -s http://localhost:8181/api/tutorials | python3 -c "import json,sys; print(f'Tutorials: {len(json.load(sys.stdin))}')"
curl -s -o /dev/null -w 'HTML: %{http_code}\n' http://localhost:8181/
kill %1
```

Expected:
```
Nodes: 31, Edges: 26
Tutorials: 6
HTML: 200
```

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```
