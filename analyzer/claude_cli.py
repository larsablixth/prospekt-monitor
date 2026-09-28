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
        self.binary  = find_binary(config)

    def _call_api(self, prompt: str) -> str:
        return run_claude(self.binary, self.model, SYSTEM_PROMPT, prompt, self.timeout)


def find_binary(config: dict) -> str:
    """Returnerar sökväg till `claude` från config eller PATH."""
    binary = config.get("binary") or shutil.which("claude")
    if not binary:
        raise RuntimeError(
            "Hittar inte 'claude' i PATH. Installera Claude Code eller "
            "ange full sökväg under ai_providers.claude_cli.binary"
        )
    return binary


def run_claude(binary: str, model: str, system_prompt: str, prompt: str, timeout: int) -> str:
    """Kör `claude -p` en gång och returnerar modellens svar som text."""
    # Ta bort API-nycklar så att CLI:t garanterat använder prenumerationen
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

    cmd = [
        binary, "-p",
        "--model", model,
        "--system-prompt", system_prompt,
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
            timeout=timeout,
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
