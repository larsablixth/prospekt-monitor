"""analyzer/gemini.py — Google Gemini-implementation."""

import google.generativeai as genai
from .base import BaseAnalyzer, SYSTEM_PROMPT


class GeminiAnalyzer(BaseAnalyzer):
    name = "gemini"

    def __init__(self, config: dict):
        genai.configure(api_key=config["api_key"])
        self.model = genai.GenerativeModel(
            model_name=config.get("model", "gemini-1.5-pro"),
            system_instruction=SYSTEM_PROMPT,
        )

    def _call_api(self, prompt: str) -> str:
        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=2048,
                response_mime_type="application/json",
            ),
        )
        return response.text
