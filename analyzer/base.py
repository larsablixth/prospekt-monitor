"""
analyzer/base.py — Gemensamt interface och analyseprompt för alla AI-providers.

Varje provider-klass ärver BaseAnalyzer och implementerar _call_api().
"""

import json
import logging
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Du är en erfaren aktieanalytiker specialiserad på att granska
börsintroduktionsprospekt för att identifiera röda flaggor och bedöma investeringspotential.

Du svarar ALLTID med ett JSON-objekt och inget annat. Inga inledande fraser, inga markdown-kodblock."""

ANALYSIS_PROMPT_TEMPLATE = """Analysera följande utdrag ur ett börsintroduktionsprospekt
för bolaget {company} och bedöm investeringspotentialen.

Poängsätt bolaget inom följande sex kategorier och motivera kort:

1. FINANSIELL HÄLSA (max 25p)
   - Eget kapital och soliditet
   - Burn rate vs emissionslikvid (klarar de 18 månader?)
   - Going concern-kommentar från revisor
   - Revisionsanmärkning

2. ÄGARSTRUKTUR (max 20p)
   - Säljer insiders aktier i noteringen (varningssignal)?
   - Lock-up-åtaganden från huvudägare
   - Utspädning för befintliga ägare
   - Komplexa holdingstrukturer / skatteparadis

3. LEDNING & STYRELSE (max 15p)
   - Track record — seriebolagsbyggare med misslyckanden?
   - VD och nyckelpersoners equity stake
   - Styrelsekomposition — branschrelevans
   - Hög personalomsättning inför notering

4. AFFÄRSMODELL (max 20p)
   - Kundkoncentration (>50% på en kund = röd flagg)
   - IP-ägande — äger bolaget sin teknologi?
   - Intäkter och väg till lönsamhet
   - Kopierad eller bevisad affärsmodell

5. PROSPEKTKVALITET (max 10p)
   - Konkreta milstolpar post-notering med tidplan
   - Redovisade antaganden bakom prognoser
   - Specifika och relevanta riskbeskrivningar (inte copy-paste)
   - Tydlig användning av emissionslikvid

6. MARKNAD & TIMING (max 10p)
   - Adresserbar marknad med trovärdiga siffror
   - Konkurrensbild — hur tar man marknadsandel?
   - Branschtrend gynnar bolaget

---

PROSPEKTUTDRAG:

{sections_text}

---

Svara med exakt detta JSON-format:

{{
  "company": "{company}",
  "total_score": <0-100>,
  "verdict": "<Gå vidare|Tveksamt|Undvik>",
  "summary": "<2-3 meningar om bolagets styrkor och svagheter>",
  "categories": {{
    "finansiell_hälsa":   {{"score": <0-25>, "comment": "<kort motivering>"}},
    "ägarstruktur":       {{"score": <0-20>, "comment": "<kort motivering>"}},
    "ledning_styrelse":   {{"score": <0-15>, "comment": "<kort motivering>"}},
    "affärsmodell":       {{"score": <0-20>, "comment": "<kort motivering>"}},
    "prospektkvalitet":   {{"score": <0-10>, "comment": "<kort motivering>"}},
    "marknad_timing":     {{"score": <0-10>, "comment": "<kort motivering>"}}
  }},
  "red_flags": [
    "<konkret oroande observation med citat från prospektet>",
    "<ytterligare röd flagg om sådan finns>"
  ],
  "green_flags": [
    "<konkret positiv observation>"
  ]
}}"""


def build_prompt(company: str, sections: dict[str, str]) -> str:
    sections_text = ""
    section_labels = {
        "riskfaktorer":           "RISKFAKTORER",
        "finansiell_information": "FINANSIELL INFORMATION",
        "ägarförhållanden":       "ÄGARFÖRHÅLLANDEN",
        "styrelse_och_ledning":   "STYRELSE OCH LEDNING",
        "emissionslikvid":        "ANVÄNDNING AV EMISSIONSLIKVID",
    }
    for key, label in section_labels.items():
        text = sections.get(key, "")
        if text:
            sections_text += f"\n### {label}\n{text}\n"
        else:
            sections_text += f"\n### {label}\n[Avsnittet hittades inte i dokumentet]\n"

    # Extra avsnitt som bara läsaren (analyzer/reader.py) plockar ut
    optional_labels = {
        "affärsmodell":           "AFFÄRSMODELL",
        "marknad_och_konkurrens": "MARKNAD OCH KONKURRENS",
    }
    for key, label in optional_labels.items():
        text = sections.get(key, "")
        if text:
            sections_text += f"\n### {label}\n{text}\n"

    return ANALYSIS_PROMPT_TEMPLATE.format(
        company=company,
        sections_text=sections_text,
    )


class BaseAnalyzer(ABC):
    """Basklass för AI-analyzers."""

    name: str = "base"

    def analyze(self, company: str, sections: dict[str, str]) -> dict:
        prompt = build_prompt(company, sections)
        try:
            raw = self._call_api(prompt)
            result = json.loads(raw)
            # Sätt verdict baserat på poäng om det saknas
            if "verdict" not in result:
                score = result.get("total_score", 0)
                result["verdict"] = (
                    "Gå vidare" if score >= 70 else
                    "Tveksamt"  if score >= 40 else
                    "Undvik"
                )
            log.info(f"{self.name}: {company} → {result['total_score']}p ({result['verdict']})")
            return result
        except json.JSONDecodeError as e:
            log.error(f"{self.name}: JSON-parsning misslyckades: {e}\nRåsvar: {raw[:500]}")
            return self._error_result(company, f"JSON-fel: {e}")
        except Exception as e:
            log.error(f"{self.name}: analys misslyckades för {company}: {e}")
            return self._error_result(company, str(e))

    @abstractmethod
    def _call_api(self, prompt: str) -> str:
        """Anropar AI-API:t och returnerar råsvaret som sträng."""
        ...

    @staticmethod
    def _error_result(company: str, error: str) -> dict:
        return {
            "company": company,
            "total_score": 0,
            "verdict": "Undvik",
            "summary": f"Analys misslyckades: {error}",
            "categories": {},
            "red_flags": [f"Tekniskt fel: {error}"],
            "green_flags": [],
        }
