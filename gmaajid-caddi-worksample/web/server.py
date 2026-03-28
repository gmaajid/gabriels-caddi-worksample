"""FastAPI server for the CADDi web application.

Serves static files, REST API for graph/tutorial data, and a multiplexed
WebSocket for terminal I/O, graph updates, and tutorial events.
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TUTORIALS_DIR = WEB_DIR / "tutorials"
PROJECT_ROOT = WEB_DIR.parent

# Ensure project root in path for imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Module-level state (single-user for Phase 2a)
_state = {
    "pty": None,
    "tutorial_engine": None,
    "graph_data": None,
    "clients": [],
}


def _build_graph_data() -> dict:
    """Build graph JSON from current project state."""
    try:
        from rag.cli import _build_viz_data
        return _build_viz_data()
    except Exception as e:
        return {"nodes": [], "edges": [], "alerts": [], "error": str(e)}


def _compute_diff(old: dict, new: dict) -> dict:
    """Compute diff between two graph states."""
    old_ids = {n["id"] for n in (old or {}).get("nodes", [])}
    new_ids = {n["id"] for n in new.get("nodes", [])}
    old_edges = {f"{e.get('source','')}->{e.get('target','')}" for e in (old or {}).get("edges", [])}
    new_edges = {f"{e.get('source','')}->{e.get('target','')}" for e in new.get("edges", [])}
    return {
        "added_nodes": list(new_ids - old_ids),
        "removed_nodes": list(old_ids - new_ids),
        "added_edges": list(new_edges - old_edges),
        "removed_edges": list(old_edges - new_edges),
    }


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    # Eagerly initialize tutorial engine so it's available even without lifespan
    # (e.g. TestClient used without context manager).
    from web.tutorial_engine import TutorialEngine
    _state["tutorial_engine"] = TutorialEngine(TUTORIALS_DIR)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _state["graph_data"] = _build_graph_data()
        yield
        # Shutdown
        pty = _state.get("pty")
        if pty:
            pty.close()

    app = FastAPI(title="CADDi Entity Resolution", lifespan=lifespan)

    # Static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/graph")
    async def get_graph():
        return _state.get("graph_data") or {"nodes": [], "edges": [], "alerts": []}

    @app.get("/api/tutorials")
    async def list_tutorials():
        engine = _state.get("tutorial_engine")
        return engine.list_tutorials() if engine else []

    @app.get("/api/tutorials/{tutorial_id}")
    async def get_tutorial(tutorial_id: str):
        engine = _state.get("tutorial_engine")
        if engine:
            t = engine.get_tutorial(tutorial_id)
            if t:
                return t
        return JSONResponse(status_code=404, content={"error": "Tutorial not found"})

    # WebSocket handler
    @app.websocket("/ws")
    async def websocket_handler(websocket: WebSocket):
        from web.pty_manager import PTYManager

        await websocket.accept()
        _state["clients"].append(websocket)

        # Spawn PTY if needed
        pty = _state.get("pty")
        if pty is None or not pty.is_alive():
            pty = PTYManager(working_dir=str(PROJECT_ROOT))
            pty.spawn()
            _state["pty"] = pty

        async def pty_reader():
            while True:
                try:
                    output = pty.read_available()
                    if output:
                        await websocket.send_text(json.dumps({
                            "channel": "terminal",
                            "type": "terminal-output",
                            "data": {"data": output.decode("utf-8", errors="replace")},
                        }))
                        output_str = output.decode("utf-8", errors="replace")
                        if pty.detect_prompt(output_str):
                            cmd = pty._current_command
                            if cmd and pty.is_state_changing_command(cmd):
                                old_graph = _state.get("graph_data")
                                _state["graph_data"] = _build_graph_data()
                                diff = _compute_diff(old_graph, _state["graph_data"])
                                update = dict(_state["graph_data"])
                                update["diff"] = diff
                                for client in list(_state["clients"]):
                                    try:
                                        await client.send_text(json.dumps({
                                            "channel": "graph",
                                            "type": "graph-updated",
                                            "data": update,
                                        }))
                                    except Exception:
                                        pass
                                pty._current_command = ""
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
                        pty.write(data.get("data", "").encode("utf-8"))
                    elif msg_type == "terminal-resize":
                        pty.resize(data.get("cols", 80), data.get("rows", 24))

                elif channel == "graph":
                    if msg_type == "graph-request":
                        _state["graph_data"] = _build_graph_data()
                        await websocket.send_text(json.dumps({
                            "channel": "graph",
                            "type": "graph-updated",
                            "data": _state["graph_data"],
                        }))

                elif channel == "tutorial":
                    engine = _state.get("tutorial_engine")
                    if engine:
                        if msg_type == "tutorial-start":
                            step = engine.start(data["id"], mode=data.get("mode", "animated"))
                            await websocket.send_text(json.dumps({"channel": "tutorial", "type": "tutorial-step", "data": step}))
                        elif msg_type == "tutorial-next":
                            step = engine.next_step()
                            await websocket.send_text(json.dumps({"channel": "tutorial", "type": "tutorial-step", "data": step}))
                        elif msg_type == "tutorial-prev":
                            step = engine.prev_step()
                            await websocket.send_text(json.dumps({"channel": "tutorial", "type": "tutorial-step", "data": step}))

        except WebSocketDisconnect:
            pass
        finally:
            reader_task.cancel()
            if websocket in _state["clients"]:
                _state["clients"].remove(websocket)

    return app
