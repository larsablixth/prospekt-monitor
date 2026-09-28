"""analyzer/claude_cli.py — Claude via Claude Code CLI (`claude -p`).

Använder din Claude Pro/Max-prenumeration i stället för API-nyckel.
Kräver att `claude` är installerat och inloggat för samma användare som
kör tjänsten (kör `claude` interaktivt en gång, eller `claude setup-token`).
"""

import json
import os
import shutil
import subprocess
import tempfile

from .base import BaseAnalyzer, SYSTEM_PROMPT


class ClaudeCliAnalyzer(BaseAnalyzer):
    name = "claude"

    def __init__(self, config: dict):
        self.model   = config.get("model", "opus")
        self.timeout = int(config.get("timeout_seconds", 600))
        self.binary  = config.get("binary") or shutil.which("claude")
        if not self.binary:
            raise RuntimeError(
                "Hittar inte 'claude' i PATH. Installera Claude Code eller "
                "ange full sökväg under ai_providers.claude_cli.binary"
            )

    def _call_api(self, prompt: str) -> str:
        # Ta bort API-nycklar så att CLI:t garanterat använder prenumerationen
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)

        cmd = [
            self.binary, "-p",
            "--model", self.model,
            "--system-prompt", SYSTEM_PROMPT,
            "--output-format", "json",
            "--max-turns", "1",
        ]

        # Kör i en tom katalog så att Claude inte läser in projektfiler
        with tempfile.TemporaryDirectory() as workdir:
            proc = subprocess.run(
                cmd,
                input=prompt,            # prospekttexten via stdin
                capture_output=True,
                text=True,
                env=env,
                cwd=workdir,
                timeout=self.timeout,
            )

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude -p avslutades med kod {proc.returncode}: "
                f"{(proc.stderr or proc.stdout)[:500]}"
            )

        envelope = json.loads(proc.stdout)
        if envelope.get("is_error"):
            raise RuntimeError(f"claude -p fel: {envelope.get('result', envelope)}")

        return _strip_code_fences(envelope.get("result", ""))


def _strip_code_fences(text: str) -> str:
    """Tar bort ```json ... ``` om modellen ändå lagt till kodblock."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()
