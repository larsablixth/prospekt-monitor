"""analyzer/openai.py — OpenAI GPT-implementation."""

from openai import OpenAI
from .base import BaseAnalyzer, SYSTEM_PROMPT


class OpenAIAnalyzer(BaseAnalyzer):
    name = "openai"

    def __init__(self, config: dict):
        self.client = OpenAI(api_key=config["api_key"])
        self.model  = config.get("model", "gpt-4.1")

    def _call_api(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
