# Phase 2a: Interactive Web Application — Design Specification

## Table of Contents

- [1. Overview](#1-overview)
- [2. Goals and Non-Goals](#2-goals-and-non-goals)
- [3. Architecture](#3-architecture)
  - [3.1 System Diagram](#31-system-diagram)
  - [3.2 Backend: FastAPI + WebSocket](#32-backend-fastapi--websocket)
  - [3.3 Frontend: D3.js + xterm.js](#33-frontend-d3js--xtermjs)
  - [3.4 Communication Protocol](#34-communication-protocol)
- [4. Embedded Terminal](#4-embedded-terminal)
  - [4.1 PTY Management](#41-pty-management)
  - [4.2 Command Detection](#42-command-detection)
  - [4.3 State Change Events](#43-state-change-events)
- [5. Interactive Tutorials](#5-interactive-tutorials)
  - [5.1 Tutorial Definition Format](#51-tutorial-definition-format)
  - [5.2 Animated Mode](#52-animated-mode)
  - [5.3 Terminal-Driven Mode](#53-terminal-driven-mode)
  - [5.4 Chain Traversal Animation](#54-chain-traversal-animation)
- [6. Graph Enhancements](#6-graph-enhancements)
  - [6.1 Edge Weight Display (Togglable)](#61-edge-weight-display-togglable)
  - [6.2 Animated Transitions](#62-animated-transitions)
  - [6.3 Diff Rendering](#63-diff-rendering)
- [7. File Structure](#7-file-structure)
- [8. Dependencies](#8-dependencies)
- [9. Deployment](#9-deployment)
- [10. Phase 2b Preview: Multi-User via Containers](#10-phase-2b-preview-multi-user-via-containers)

---

## 1. Overview

Phase 2a evolves the static web visualization into a full interactive web application. The web interface becomes the primary way to interact with the system, with three integrated panels: entity relationship graph, guided tutorials, and a live terminal.

Tutorials drive the graph — highlighting nodes, animating chain traversals, and zooming to relevant areas. The terminal lets users run any `caddi-cli` command, and the graph updates in real-time when commands change state.

Two tutorial modes: **Animated** (auto-navigate, hands-off presentation) and **Terminal-Driven** (user runs commands, graph reacts live).

**Context:** This is for the 30-60 minute CADDi demo interview. The interviewer sees a polished web application where the graph comes alive as you walk through scenarios.

---

## 2. Goals and Non-Goals

### Goals

- Embedded full terminal (xterm.js) for running any caddi-cli command
- Interactive tutorials that control the graph (zoom, highlight, animate chains)
- Two tutorial modes: animated (presentation) and terminal-driven (hands-on)
- Real-time graph updates when terminal commands change M&A registry or mappings
- Chain traversal animation showing resolution path step-by-step
- Edge weight labels (J/E/C scores) togglable on/off
- Single Docker image deployment (same as Phase 1)

### Non-Goals

- Multi-user support (Phase 2b — containerized user sessions)
- User authentication or authorization
- Persistent user state across browser sessions
- Mobile responsive layout (desktop demo only)
- Editing the M&A registry through the graph UI (use terminal)

---

## 3. Architecture

### 3.1 System Diagram

The application has three layers:

**Browser (client):**
- D3.js force-directed graph with animation support
- xterm.js terminal emulator
- Tutorial engine (step controller + animation sequencer)
- All three panels communicate via a shared WebSocket connection

**FastAPI Server (backend):**
- Static file serving for HTML/JS/CSS
- REST API for graph data and tutorial definitions
- WebSocket hub: terminal I/O + graph state events + tutorial commands
- PTY manager: spawns and manages the bash shell process

**PTY Process (shell):**
- Bash shell with venv activated
- Runs caddi-cli commands
- Output streams back to browser via WebSocket

### 3.2 Backend: FastAPI + WebSocket

```python
# web/server.py — simplified structure

app = FastAPI()

# Static files
app.mount("/static", StaticFiles(directory="web/static"))

# REST endpoints
@app.get("/api/graph")      # graph node/edge data
@app.get("/api/tutorials")  # tutorial list
@app.get("/api/tutorials/{id}")  # single tutorial definition

# WebSocket — multiplexed for terminal + graph events
@app.websocket("/ws")
async def websocket_handler(ws: WebSocket):
    # Messages have a "channel" field: "terminal", "graph", "tutorial"
    # Terminal channel: relay keystrokes to PTY, output back to browser
    # Graph channel: push state-changed events when commands complete
    # Tutorial channel: push resolution-trace events for animations
```

### 3.3 Frontend: D3.js + xterm.js

The page has a three-panel layout:

```
┌──────────────────────────────────────────────────────────────┐
│  CADDi Entity Resolution          [Graph] [Tutorials] [☰]   │
├────────────┬─────────────────────────────────────────────────┤
│            │                                                 │
│  Sidebar   │              Graph / Tutorial View              │
│  - Filters │              (switches based on tab)            │
│  - Details │                                                 │
│  - Legend  │                                                 │
│  - Weights │                                                 │
│    toggle  │                                                 │
│            │                                                 │
│            ├─────────────────────────────────────────────────┤
│            │                                                 │
│            │              Terminal Panel                     │
│            │              (xterm.js, resizable)              │
│            │                                                 │
├────────────┴─────────────────────────────────────────────────┤
│  Status bar: connected | 31 nodes, 26 edges | Tutorial 3/6  │
└──────────────────────────────────────────────────────────────┘
```

- The terminal panel is at the bottom, resizable via drag handle
- Graph and tutorials share the main content area (tab switch)
- Sidebar persists across all views

### 3.4 Communication Protocol

All WebSocket messages use this envelope:

```json
{
  "channel": "terminal" | "graph" | "tutorial",
  "type": "<event-type>",
  "data": { ... }
}
```

**Terminal channel messages:**

| Direction | Type | Data |
|-----------|------|------|
| Client → Server | `terminal-input` | `{"data": "caddi-cli ma list\r"}` |
| Server → Client | `terminal-output` | `{"data": "\x1b[32m...\x1b[0m"}` |
| Client → Server | `terminal-resize` | `{"cols": 120, "rows": 30}` |

**Graph channel messages:**

| Direction | Type | Data |
|-----------|------|------|
| Server → Client | `graph-updated` | `{"nodes": [...], "edges": [...], "diff": {"added": [], "removed": []}}` |
| Server → Client | `resolution-trace` | `{"input": "AQF Holdings", "chain": [...]}` |
| Client → Server | `graph-request` | `{}` (explicit refresh request) |

**Tutorial channel messages:**

| Direction | Type | Data |
|-----------|------|------|
| Client → Server | `tutorial-start` | `{"id": "03_acquisition", "mode": "animated"}` |
| Server → Client | `tutorial-step` | `{"step": 3, "highlight_nodes": [...], "zoom_to": "...", "command": "..."}` |
| Client → Server | `tutorial-next` | `{}` |
| Client → Server | `tutorial-prev` | `{}` |
| Server → Client | `tutorial-command-output` | `{"command": "...", "output": "..."}` |

---

## 4. Embedded Terminal

### 4.1 PTY Management

```python
# web/pty_manager.py

class PTYManager:
    """Manages a pseudo-terminal running a bash shell."""

    def __init__(self, working_dir: str, venv_path: str):
        # Fork a PTY process
        # Set environment: PATH includes venv/bin, TERM=xterm-256color
        # Start bash with --login to get proper prompt

    async def read(self) -> bytes:
        """Non-blocking read from PTY output."""

    def write(self, data: bytes) -> None:
        """Write input to PTY (keystrokes from browser)."""

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window."""

    def detect_command_complete(self, output: str) -> Optional[str]:
        """Detect when a caddi-cli command finishes by watching for the shell prompt."""
```

The PTY spawns with:
- Working directory: project root
- `PATH` includes `.venv/bin`
- `VIRTUAL_ENV` set
- `TERM=xterm-256color` for color support
- Custom `PS1` prompt that's easy to detect programmatically

### 4.2 Command Detection

The PTY manager watches the output stream for patterns:

1. **Shell prompt returns** — after a command runs, the prompt reappears (e.g., `$ `)
2. **Command was caddi-cli** — the manager buffers the command line and checks if it starts with `caddi-cli` or `./caddi-cli`
3. **State-changing commands** — only these trigger a graph refresh:
   - `caddi-cli ma add|remove` — M&A registry changed
   - `caddi-cli ingest` — RAG state changed
   - `caddi-cli demo generate` — demo data changed
   - `caddi-cli mappings` — not state-changing, no refresh needed

### 4.3 State Change Events

When a state-changing command completes:

1. The PTY manager notifies the server
2. The server rebuilds the graph data (calls `_build_viz_data()`)
3. The server computes a diff against the previous graph state
4. The server pushes a `graph-updated` event via WebSocket with the full graph + diff
5. The client D3.js graph animates the diff (new nodes fade in, removed nodes fade out, changed edges transition)

---

## 5. Interactive Tutorials

### 5.1 Tutorial Definition Format

Each tutorial is a YAML file in `web/tutorials/`, loaded once at server startup (FastAPI lifespan event). Tutorials don't change during a session — hot-reload is not needed.

```yaml
# web/tutorials/03_acquisition.yaml
id: "03_acquisition"
title: "Post-Acquisition Resolution"
tier: 3
description: "How the system resolves names after Apex acquired QuickFab"
steps:
  - step: 1
    title: "The Acquisition"
    narrative: >
      In July 2024, Apex Manufacturing acquired QuickFab Industries.
      After the acquisition, orders started appearing under new names
      like 'Apex-QuickFab Industries' and 'AQF Holdings'.
    highlight_nodes: ["Apex Manufacturing", "QuickFab Industries"]
    highlight_edges: []
    zoom_to: "Apex Manufacturing"
    command: null

  - step: 2
    title: "View the M&A Event"
    narrative: >
      Let's look at the acquisition event in the registry.
    highlight_nodes: ["Apex Manufacturing"]
    highlight_edges: ["ma"]
    zoom_to: "Apex Manufacturing"
    command: "caddi-cli ma show ma-1c52b8"
    expected_output_contains: "acquisition"

  - step: 3
    title: "Trace the Resolution"
    narrative: >
      Watch how 'AQF Holdings' resolves back to 'Apex Manufacturing'
      through the M&A chain.
    resolution_trace:
      input: "AQF Holdings"
      chain:
        - node: "AQF Holdings"
          action: "start"
          delay_ms: 0
        - edge: "AQF Holdings → Apex Manufacturing"
          type: "ma"
          weight: 1.0
          event_id: "ma-1c52b8"
          event_date: "2024-07-15"
          delay_ms: 800
        - node: "Apex Manufacturing"
          action: "resolved"
          delay_ms: 1600
    command: "caddi-cli demo run --extended"

  - step: 4
    title: "What If We Remove the Event?"
    narrative: >
      Without the M&A registry entry, the system can't resolve
      'AQF Holdings' — there's zero token overlap with 'Apex Manufacturing'.
      Watch the benchmark scores drop.
    command: null
    note: "In terminal-driven mode, the user runs: caddi-cli ma remove ma-1c52b8"
```

### 5.2 Animated Mode

When a tutorial starts in animated mode:

1. The tutorial engine loads the YAML definition
2. For each step, it pushes events to the browser:
   - `tutorial-step` with narrative text and graph instructions
   - The graph zooms/pans to `zoom_to` node (smooth D3 transition, 500ms)
   - `highlight_nodes` and `highlight_edges` get CSS class `tutorial-active` (pulsing glow)
   - If `command` is set, it's auto-executed in the terminal (typewriter effect at 50ms/char)
   - If `resolution_trace` is set, the chain animation plays (see 5.4)
3. The user clicks "Next Step" to advance (or it auto-advances after animation completes)
4. Between steps, highlights clear and the graph returns to normal state

### 5.3 Terminal-Driven Mode

Same tutorial YAML, different execution:

1. Each step shows the narrative and the command to run
2. The command appears as a copyable code block (click to paste into terminal)
3. The user types/pastes the command in the terminal
4. The PTY manager detects the command completing
5. If `expected_output_contains` is set, the tutorial checks the output
6. The graph reacts via the normal state-change event pipeline
7. The tutorial advances when the expected state change is detected (or the user clicks "Next")

### 5.4 Chain Traversal Animation

When a `resolution_trace` is triggered (from tutorial or from a `caddi-cli demo run`):

1. **Start node pulses** — target node gets class `trace-start`, amber glow, 500ms
2. **Edge animates** — SVG animated circle travels along the edge path at constant speed. Edge weight label fades in alongside. Edge gets class `trace-active` (brighter, thicker).
3. **Event badge** — if the edge is an M&A edge, a small tooltip appears: "acquisition 2024-07-15"
4. **Delay** — configurable `delay_ms` between hops (default 800ms)
5. **Next hop** — repeat for next edge in chain
6. **Destination pulses** — final node gets class `trace-resolved`, green glow, 1000ms
7. **Path persists** — full chain stays highlighted for 3 seconds, then fades

For **split votes**:
1. Input node pulses amber
2. Two (or more) pulses fork along different edges simultaneously
3. Edge weight labels show vote weights
4. The winning path brightens (green), losing path dims (gray)
5. Winner's destination node pulses green

The animation is interruptible — clicking anywhere or pressing Escape cancels it.

---

## 6. Graph Enhancements

### 6.1 Edge Weight Display (Togglable)

A checkbox in the sidebar: **"Show Edge Weights"**

When enabled:
- Each edge gets a text label at its midpoint: `J=0.85 E=0.72 C=0.92`
- M&A edges show: `M&A 1.0` + event date
- Division edges show: `div`
- Labels use small font (10px), semi-transparent, positioned to avoid overlap
- Color-coded: green (C ≥ 0.85), yellow (0.55-0.85), red (< 0.55)

When disabled:
- Labels hidden (default state for clean presentation)
- Weights still visible on hover and in the detail panel

State persisted to `localStorage`.

### 6.2 Animated Transitions

When the graph receives a `graph-updated` event with a diff:

- **New nodes**: fade in from transparent (opacity 0 → 1, 500ms) at their force-computed position
- **Removed nodes**: fade out (opacity 1 → 0, 300ms) then removed from DOM
- **New edges**: draw from source to target (stroke-dashoffset animation, 400ms)
- **Removed edges**: fade out (300ms)
- **Changed edges** (score updated): weight label transitions to new value with color change

### 6.3 Diff Rendering

After a `graph-updated` event, a transient banner appears at the top of the graph:

```
+2 nodes, -1 node, ~3 edges changed
```

Fades out after 3 seconds. Clicking it opens a diff panel showing exactly what changed (similar to `caddi-cli diff` output).

---

## 7. File Structure

```
web/
  server.py              — FastAPI app, routes, WebSocket hub
  pty_manager.py         — PTY spawn/manage, command detection
  tutorial_engine.py     — Load tutorial YAML, manage step state, emit events
  static/                — Client-side assets
    index.html           — Main page layout
    css/
      style.css          — Layout, colors, panels
      graph.css          — Node/edge styles, animation keyframes
      terminal.css       — xterm.js overrides
      tutorial.css       — Tutorial panel, step cards
    js/
      app.js             — WebSocket connection, message routing
      graph.js           — D3.js graph rendering + animation
      terminal.js        — xterm.js setup + resize handling
      tutorial.js        — Tutorial UI, mode toggle, step controller
      animation.js       — Chain traversal animation, diff transitions
    lib/                 — Vendored JS libraries (no CDN dependency)
      d3.v7.min.js
      xterm.min.js
      xterm-addon-fit.min.js
      xterm-addon-web-links.min.js
  tutorials/             — Tutorial definition YAML files
    01_abbreviations.yaml
    02_typos.yaml
    03_acquisition.yaml
    04_rebrand.yaml
    05_broken_chains.yaml
    06_divisions.yaml
```

---

## 8. Dependencies

New Python dependencies (add to `pyproject.toml`):

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
websockets>=13.0
```

Client-side libraries (vendored in `web/static/lib/`, no CDN required for offline/Docker):

```
d3.js v7           — graph rendering
xterm.js 5.x       — terminal emulator
xterm-addon-fit     — auto-resize terminal to container
xterm-addon-web-links — clickable URLs in terminal output
```

No new system dependencies. The PTY is managed via Python's `pty` and `os` modules (stdlib).

---

## 9. Deployment

Same Docker image as Phase 1, with two changes:

1. Install `fastapi` + `uvicorn` + `websockets` (added to pyproject.toml)
2. Vendor xterm.js files into `web/static/lib/` at build time (or commit them)

The `caddi-cli viz` command changes from `http.server` to:

```python
uvicorn.run("web.server:app", host="0.0.0.0", port=port)
```

Docker runs:
```bash
docker run -it -p 8080:8080 caddi-demo viz
```

Everything else unchanged — single image, no external services.

---

## 10. Phase 2b Preview: Multi-User via Containers

Not implemented in Phase 2a, but the architecture is designed for it:

- Each user session spawns a container from the same image
- The container runs the FastAPI server on an internal port
- A reverse proxy (nginx/traefik) routes users to their container
- Container state = user state (config/, data/, chroma_db/)
- Serialize: `docker commit <container>` or volume snapshot
- Deserialize: `docker run` from committed image or mount snapshot
- Session timeout: container stopped after N minutes of inactivity
- No shared state between users — complete isolation

The only Phase 2a code that changes for Phase 2b is the entry point — instead of running FastAPI directly, a lightweight orchestrator manages container lifecycle.
