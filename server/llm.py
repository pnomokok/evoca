"""
LLM abstraction for the Evoca chat agent.

Classes
-------
LLM             Protocol — one method: converse(system, messages, tools)
BedrockLLM      Real implementation using boto3 bedrock-runtime.
RecordingLLM    Wraps any LLM and records every request (for leak tests).

Utilities
---------
strip_thinking  Remove <thinking>…</thinking> blocks Nova Pro emits.
"""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

import boto3

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

_THINKING_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Remove <thinking>…</thinking> blocks that Nova Pro emits."""
    return _THINKING_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class LLM(Protocol):
    def converse(
        self,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call the model synchronously and return a Bedrock Converse response dict."""
        ...


# ---------------------------------------------------------------------------
# BedrockLLM
# ---------------------------------------------------------------------------

class BedrockLLM:
    """Calls Amazon Bedrock Converse API using boto3 (synchronous).

    Configuration via environment variables:
      BEDROCK_REGION    — AWS region (default: us-east-1)
      EVOCA_CHAT_MODEL  — model ID  (default: us.amazon.nova-2-lite-v1:0)
    """

    def __init__(self) -> None:
        region = os.environ.get("BEDROCK_REGION", "us-east-1")
        self.model_id = os.environ.get(
            "EVOCA_CHAT_MODEL", "us.amazon.nova-2-lite-v1:0"
        )
        self._client = boto3.Session(region_name=region).client("bedrock-runtime")

    def converse(
        self,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": system,
            "messages": messages,
            "inferenceConfig": {"maxTokens": 1024},
        }
        if tools:
            kwargs["toolConfig"] = tools
        response = self._client.converse(**kwargs)

        # Strip <thinking> blocks from every text block in the response.
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                block["text"] = strip_thinking(block["text"])

        return response


# ---------------------------------------------------------------------------
# RecordingLLM
# ---------------------------------------------------------------------------

class RecordingLLM:
    """Wraps any LLM and keeps a copy of every request payload.

    Used in the privacy-leak test to verify that private segment transcripts
    never appear in anything sent to the model.
    """

    def __init__(self, inner: LLM) -> None:
        self._inner = inner
        self.requests: list[dict[str, Any]] = []

    def converse(
        self,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.requests.append(
            {"system": system, "messages": messages, "tools": tools}
        )
        return self._inner.converse(system, messages, tools)
