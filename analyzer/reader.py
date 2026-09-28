"""analyzer/reader.py — Snabb "läsare" som går igenom hela prospektet.

En snabb, billig modell (t.ex. Haiku) läser hela prospekttexten i delar och
plockar ut det som är relevant för analysen. Resultatet har samma form som
pdf_extractor.extract_sections(), så analysmodellen (t.ex. Opus) får
koncentrerat innehåll i stället för första rubrikträffen.

Använder Claude Code (`claude -p`) och prenumerationen, precis som claude_cli.
"""

import json
import logging

from .claude_cli import find_binary, run_claude

log = logging.getLogger(__name__)

READER_SYSTEM_PROMPT = """Du är en noggrann läsare av börsintroduktionsprospekt.
Du plockar ut fakta — du analyserar och värderar inte.

Du svarar ALLTID med ett JSON-objekt och inget annat. Inga inledande fraser, inga markdown-kodblock."""

# Avsnitt → vad läsaren ska leta efter
READER_SECTIONS = {
    "riskfaktorer":
        "bolagsspecifika risker (inte generisk standardtext), going concern-kommentarer, "
        "revisionsanmärkningar, pågående tvister",
    "finansiell_information":
        "omsättning, resultat, kassaflöde, eget kapital, soliditet, kassa, burn rate, "
        "skulder — med år/period för varje siffra",
    "ägarförhållanden":
        "största ägare före/efter erbjudandet, insiders som säljer aktier i erbjudandet, "
        "lock-up (vem, hur länge), utspädning, teckningsåtaganden och garanter, "
        "holdingbolag och säten utomlands",
    "styrelse_och_ledning":
        "namn och roll, bakgrund och tidigare bolag (även konkurser/misslyckanden), "
        "aktieinnehav, incitamentsprogram, nyligen avgångna nyckelpersoner",
    "emissionslikvid":
        "emissionsbelopp, emissionskostnader, hur likviden ska användas, hur länge den "
        "beräknas räcka, milstolpar med tidplan",
    "affärsmodell":
        "vad bolaget säljer och till vem, intäktskällor, största kundernas andel av "
        "intäkterna, IP/patent och vem som äger dem, väg till lönsamhet",
    "marknad_och_konkurrens":
        "marknadsstorlek och källan till siffrorna, konkurrenter, marknadstrender",
}

READER_PROMPT_TEMPLATE = """Nedan är del {part} av {total} av prospektet för {company}.

Plocka ut det som är relevant för varje avsnitt. Regler:
- Citera ordagrant eller nästan ordagrant.
- Behåll ALLA siffror, belopp, procentsatser, datum och namn exakt.
- Hoppa över innehållsförteckning, definitioner och juridisk standardtext.
- Finns inget relevant i denna del: lämna strängen tom.
- Högst ca {max_chars} tecken per avsnitt.

Avsnitt och vad du ska leta efter:
{section_list}

Svara med exakt detta JSON-format:
{json_skeleton}

--- PROSPEKTTEXT (del {part}/{total}) ---

{chunk}"""


class ClaudeCliReader:
    """Läser hela prospektet med en snabb modell via `claude -p`."""

    def __init__(self, config: dict):
        self.model         = config.get("model", "haiku")
        self.timeout       = int(config.get("timeout_seconds", 300))
        self.chunk_chars   = int(config.get("chunk_chars", 150_000))
        self.max_chunks    = int(config.get("max_chunks", 12))
        self.max_chars     = int(config.get("max_chars_per_section", 12_000))
        self.binary        = find_binary(config)

    def read(self, company: str, full_text: str) -> dict[str, str]:
        """
        Returnerar dict med avsnitt → utplockad text.
        Returnerar {} om ingen del gick att läsa (anroparen faller då tillbaka
        på rubriksökning).
        """
        chunks = _split_into_chunks(full_text, self.chunk_chars)
        if len(chunks) > self.max_chunks:
            log.warning(
                f"Läsare: {company} har {len(chunks)} delar, läser bara de "
                f"första {self.max_chunks} (max_chunks)"
            )
            chunks = chunks[: self.max_chunks]

        per_chunk_chars = max(1_000, self.max_chars // max(1, len(chunks)))
        collected = {key: [] for key in READER_SECTIONS}
        ok_parts = 0

        for i, chunk in enumerate(chunks, start=1):
            prompt = _build_reader_prompt(company, chunk, i, len(chunks), per_chunk_chars)
            try:
                raw = run_claude(self.binary, self.model, READER_SYSTEM_PROMPT, prompt, self.timeout)
                data = json.loads(raw)
            except Exception as e:
                log.error(f"Läsare: del {i}/{len(chunks)} misslyckades för {company}: {e}")
                continue

            ok_parts += 1
            for key in READER_SECTIONS:
                text = data.get(key)
                if isinstance(text, str) and text.strip():
                    collected[key].append(text.strip())

        if ok_parts == 0:
            return {}

        sections = {}
        for key, parts in collected.items():
            text = "\n\n".join(parts)
            if len(text) > self.max_chars:
                text = text[: self.max_chars] + "\n[... trunkerat ...]"
            sections[key] = text

        found = sum(1 for v in sections.values() if v)
        if found == 0:
            log.warning(f"Läsare: inget relevant hittades för {company}")
            return {}
        log.info(
            f"Läsare ({self.model}): {ok_parts}/{len(chunks)} delar lästa, "
            f"{found}/{len(READER_SECTIONS)} avsnitt med innehåll för {company}"
        )
        return sections


def _build_reader_prompt(company: str, chunk: str, part: int, total: int, max_chars: int) -> str:
    section_list = "\n".join(f"- {key}: {desc}" for key, desc in READER_SECTIONS.items())
    json_skeleton = json.dumps({key: "..." for key in READER_SECTIONS}, ensure_ascii=False, indent=2)
    return READER_PROMPT_TEMPLATE.format(
        company=company,
        part=part,
        total=total,
        max_chars=max_chars,
        section_list=section_list,
        json_skeleton=json_skeleton,
        chunk=chunk,
    )


def _split_into_chunks(text: str, chunk_chars: int) -> list[str]:
    """Delar texten i bitar på ungefär chunk_chars tecken, vid radbrytningar."""
    chunks, current, size = [], [], 0
    for line in text.split("\n"):
        # En enskild jätterad delas hårt så att den inte spräcker gränsen
        while len(line) > chunk_chars:
            if current:
                chunks.append("\n".join(current))
                current, size = [], 0
            chunks.append(line[:chunk_chars])
            line = line[chunk_chars:]
        if size + len(line) + 1 > chunk_chars and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current and any(l.strip() for l in current):
        chunks.append("\n".join(current))
    return chunks
