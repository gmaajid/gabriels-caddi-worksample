"""Tests for PTY manager — process lifecycle and command detection."""

import pytest
import time
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
        time.sleep(0.5)
        output = mgr.read_available()
        mgr.close()
        assert b"hello" in output

    def test_resize(self):
        mgr = PTYManager()
        mgr.spawn()
        mgr.resize(120, 40)
        mgr.close()


class TestCommandDetection:
    def test_detects_state_changing_commands(self):
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
        assert mgr.detect_prompt("some output\ncaddi> ")
        assert not mgr.detect_prompt("still running...")
