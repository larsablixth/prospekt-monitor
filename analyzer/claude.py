"""analyzer/claude.py — Anthropic Claude-implementation."""

import anthropic
from .base import BaseAnalyzer, SYSTEM_PROMPT


class ClaudeAnalyzer(BaseAnalyzer):
    name = "claude"

    def __init__(self, config: dict):
        self.client = anthropic.Anthropic(api_key=config["api_key"])
        self.model  = config.get("model", "claude-sonnet-4-6")

    def _call_api(self, prompt: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
