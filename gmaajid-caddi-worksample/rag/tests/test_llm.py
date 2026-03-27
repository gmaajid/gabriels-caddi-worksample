"""Tests for LLM integration (mocked — no API key required)."""

from unittest.mock import MagicMock, patch

from rag.llm import SYSTEM_PROMPT, ask


def test_ask_without_api_key():
    """Without ANTHROPIC_API_KEY, returns raw context with a warning."""
    with patch.dict("os.environ", {}, clear=True):
        result = ask("test question", "some context")
        assert "ANTHROPIC_API_KEY not set" in result
        assert "some context" in result


def test_ask_with_api_key():
    """With API key, calls Claude and returns the response."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Claude's answer")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("rag.llm.Anthropic", return_value=mock_client):
            result = ask("test question", "some context")

    assert result == "Claude's answer"
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["system"] == SYSTEM_PROMPT
    assert "test question" in call_kwargs["messages"][0]["content"]


def test_system_prompt_content():
    assert "Hoth Industries" in SYSTEM_PROMPT
    assert "supply chain" in SYSTEM_PROMPT
