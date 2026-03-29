"""
pdf_extractor.py — Extraherar nyckelavsnitt ur prospekt-PDF:er.

Söker efter rubriknyckelord och drar ut text från relevanta sektioner.
Returnerar en dict med avsnitt → text.
"""

import logging
import re
from pathlib import Path

from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
from io import StringIO

log = logging.getLogger(__name__)

# Nyckelord per avsnitt (svenska + engelska)
SECTION_PATTERNS = {
    "riskfaktorer": [
        r"riskfaktorer",
        r"risk factors",
        r"väsentliga risker",
    ],
    "finansiell_information": [
        r"historisk finansiell information",
        r"finansiell översikt",
        r"financial information",
        r"finansiella rapporter",
        r"resultaträkning",
    ],
    "ägarförhållanden": [
        r"ägarförhållanden",
        r"aktieägare",
        r"major shareholders",
        r"ownership structure",
    ],
    "styrelse_och_ledning": [
        r"styrelse och ledande befattningshavare",
        r"styrelse",
        r"board of directors",
        r"management",
        r"ledningsgrupp",
    ],
    "emissionslikvid": [
        r"användning av emissionslikvid",
        r"användning av likvid",
        r"use of proceeds",
        r"kapitalbehov",
    ],
}

MAX_CHARS_PER_SECTION = 8_000   # ~2 000 tokens per avsnitt


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extraherar all text från PDF."""
    try:
        output = StringIO()
        with open(pdf_path, "rb") as f:
            extract_text_to_fp(f, output, laparams=LAParams())
        return output.getvalue()
    except Exception as e:
        log.error(f"PDF-extraktion misslyckades för {pdf_path}: {e}")
        return ""


def extract_sections(pdf_path: str) -> dict[str, str]:
    """
    Returnerar dict med nyckelavsnitt → extraherad text.
    Om ett avsnitt inte hittas är värdet en tom sträng.
    """
    full_text = extract_text_from_pdf(pdf_path)
    if not full_text:
        return {}

    # Dela upp i rader för positionssökning
    lines = full_text.split("\n")
    total_lines = len(lines)

    sections = {}

    for section_name, patterns in SECTION_PATTERNS.items():
        start_line = None

        # Hitta första raden som matchar något av mönstren
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            if any(re.search(pat, line_lower) for pat in patterns):
                # Kontrollera att det är en rubrik (kort rad, inte mitt i ett stycke)
                if len(line.strip()) < 120:
                    start_line = i
                    break

        if start_line is None:
            log.debug(f"Avsnitt '{section_name}' hittades inte i {pdf_path}")
            sections[section_name] = ""
            continue

        # Ta text fram till nästa rubrik eller max MAX_CHARS_PER_SECTION tecken
        end_line = min(start_line + 300, total_lines)
        section_text = "\n".join(lines[start_line:end_line])

        # Trimma till max längd
        if len(section_text) > MAX_CHARS_PER_SECTION:
            section_text = section_text[:MAX_CHARS_PER_SECTION] + "\n[... trunkerat ...]"

        sections[section_name] = section_text.strip()
        log.debug(f"Avsnitt '{section_name}': {len(section_text)} tecken")

    found = sum(1 for v in sections.values() if v)
    log.info(f"PDF-extraktion: {found}/{len(SECTION_PATTERNS)} avsnitt hittade i {Path(pdf_path).name}")

    return sections
