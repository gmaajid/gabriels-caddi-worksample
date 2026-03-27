"""LLM integration for RAG-augmented queries using Claude."""

from __future__ import annotations

import os

from anthropic import Anthropic

SYSTEM_PROMPT = """\
You are a supply chain intelligence assistant for Hoth Industries, a manufacturer of \
air handling and cooling products for data centers. You help analyze supplier performance, \
quality data, procurement decisions, and RFQ responses.

When answering questions, use the provided context from the knowledge base. \
Cite specific data points when available. If the context doesn't contain enough \
information to answer fully, say so clearly.
"""


def ask(question: str, context: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Send a RAG-augmented question to Claude."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return (
            "ANTHROPIC_API_KEY not set. Set it in your environment to enable LLM-powered answers.\n\n"
            "Raw context from knowledge base:\n\n" + context
        )

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Context from knowledge base:\n\n{context}\n\n---\n\nQuestion: {question}"
                ),
            }
        ],
    )
    return message.content[0].text
