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
        self.venv_path = venv_path or str(Path(self.working_dir) / ".venv")
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

        master_fd, slave_fd = pty.openpty()
        child_pid = os.fork()

        if child_pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.chdir(self.working_dir)
            os.execvpe("/bin/bash", ["/bin/bash", "--norc", "--noprofile"], env)
        else:
            # Parent process
            os.close(slave_fd)
            self._master_fd = master_fd
            self._pid = child_pid
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def is_alive(self) -> bool:
        if self._pid is None:
            return False
        try:
            pid, _ = os.waitpid(self._pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def close(self) -> None:
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
        if self._master_fd is not None:
            os.write(self._master_fd, data)

    def read_available(self) -> bytes:
        if self._master_fd is None:
            return b""
        chunks = []
        while True:
            try:
                chunk = os.read(self._master_fd, 4096)
                if not chunk:
                    break
                chunks.append(chunk)
            except OSError:
                break
        return b"".join(chunks)

    def resize(self, cols: int, rows: int) -> None:
        if self._master_fd is not None:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def is_state_changing_command(self, command: str) -> bool:
        for pattern in STATE_CHANGING_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def detect_prompt(self, output: str) -> bool:
        return PROMPT_MARKER in output
