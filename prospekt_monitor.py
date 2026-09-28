"""
prospekt_monitor.py — Huvudskript.

Körordning:
  1. Hämta nya dokument från FI + Nasdaq RSS
  2. Ladda hem PDF (om tillgänglig)
  3. Extrahera nyckelavsnitt (snabb läsarmodell, annars rubriksökning)
  4. Kör AI-analys (Claude + OpenAI + Gemini)
  5. Spara i DB
  6. Skicka e-postnotis
"""

import logging
import os
import sys
from pathlib import Path

import requests
import yaml

from db import init_db, save_document, save_analysis, get_analyses
from pdf_extractor import extract_sections, extract_text_from_pdf
from scrapers.fi import fetch_new as fi_fetch
from scrapers.nasdaq_rss import fetch_new as nasdaq_fetch
from scrapers.avanza import fetch_new as avanza_fetch
import notifier
import ha_notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("prospekt_monitor.log"),
    ],
)
log = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def download_pdf(url: str, dest_dir: str, doc_id: str) -> str | None:
    """Laddar hem PDF och returnerar lokal sökväg."""
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    dest = Path(dest_dir) / f"{doc_id}.pdf"
    if dest.exists():
        return str(dest)
    try:
        r = requests.get(url, timeout=60, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        log.info(f"PDF nedladdad: {dest.name} ({dest.stat().st_size // 1024} kB)")
        return str(dest)
    except Exception as e:
        log.error(f"Nedladdning misslyckades för {url}: {e}")
        return None


def build_analyzers(config: dict) -> list:
    """Skapar aktiva AI-analyzers enligt config."""
    analyzers = []
    providers = config.get("ai_providers", {})

    if providers.get("claude", {}).get("enabled"):
        from analyzer.claude import ClaudeAnalyzer
        analyzers.append(ClaudeAnalyzer(providers["claude"]))

    if providers.get("claude_cli", {}).get("enabled"):
        from analyzer.claude_cli import ClaudeCliAnalyzer
        analyzers.append(ClaudeCliAnalyzer(providers["claude_cli"]))

    if providers.get("openai", {}).get("enabled"):
        from analyzer.openai import OpenAIAnalyzer
        analyzers.append(OpenAIAnalyzer(providers["openai"]))

    if providers.get("gemini", {}).get("enabled"):
        from analyzer.gemini import GeminiAnalyzer
        analyzers.append(GeminiAnalyzer(providers["gemini"]))

    return analyzers


def build_reader(config: dict):
    """Skapar läsaren (snabb modell som går igenom hela prospektet), eller None."""
    reader_cfg = config.get("reader", {})
    if not reader_cfg.get("enabled"):
        return None
    # Samma claude-binär som claude_cli om ingen egen anges
    cli_cfg = config.get("ai_providers", {}).get("claude_cli", {})
    if not reader_cfg.get("binary") and cli_cfg.get("binary"):
        reader_cfg = {**reader_cfg, "binary": cli_cfg["binary"]}
    from analyzer.reader import ClaudeCliReader
    try:
        return ClaudeCliReader(reader_cfg)
    except RuntimeError as e:
        log.warning(f"Läsaren avstängd: {e} — använder rubriksökning")
        return None


def process_document(doc: dict, conn, analyzers: list, config: dict, reader=None):
    """Hanterar ett nytt dokument — nedladdning, analys, notis."""
    company = doc["company"]
    log.info(f"Behandlar: {company} ({doc['source']})")

    # Spara i DB
    save_document(conn, doc)

    # Ladda hem PDF om det finns en URL som pekar på PDF
    local_path = None
    if doc["url"] and doc["doc_type"] != "rss_notice":
        local_path = download_pdf(
            doc["url"],
            config["storage"]["download_dir"],
            doc["id"],
        )
        if local_path:
            # Uppdatera local_path i DB
            conn.execute(
                "UPDATE documents SET local_path = ? WHERE id = ?",
                (local_path, doc["id"]),
            )
            conn.commit()

    # Extrahera nyckelavsnitt
    sections = {}
    if local_path:
        full_text = extract_text_from_pdf(local_path)
        if reader and full_text:
            sections = reader.read(company, full_text)
            if not sections:
                log.warning(f"Läsaren misslyckades för {company} — faller tillbaka på rubriksökning")
        if not sections:
            sections = extract_sections(local_path, full_text)
    else:
        log.info(f"Ingen PDF tillgänglig för {company} — analys på metadata")

    # Kör AI-analys
    analysis_results = []
    for analyzer in analyzers:
        result = analyzer.analyze(company, sections)
        save_analysis(conn, doc["id"], analyzer.name, result)
        analysis_results.append({
            "provider":    analyzer.name,
            "score":       result.get("total_score"),
            "verdict":     result.get("verdict"),
            "summary":     result.get("summary"),
            "full_result": result,
        })

    # Skicka notiser — e-post + HA
    if analysis_results:
        notifier.send({**doc, "local_path": local_path}, analysis_results, config)
        ha_notifier.send({**doc, "local_path": local_path}, analysis_results, config)


def run():
    config_path = os.environ.get("PROSPEKT_CONFIG", "config.yaml")
    if not Path(config_path).exists():
        log.error(f"Konfigurationsfil saknas: {config_path}")
        sys.exit(1)

    config   = load_config(config_path)
    conn     = init_db(config["storage"]["db_path"])
    analyzers = build_analyzers(config)
    reader    = build_reader(config)

    if not analyzers:
        log.warning("Inga AI-providers aktiverade i config.yaml")

    log.info("=== Prospekt Monitor startar ===")

    # Hämta nya dokument från alla källor
    new_docs = []
    new_docs.extend(fi_fetch(conn, config))
    new_docs.extend(nasdaq_fetch(conn, config))
    new_docs.extend(avanza_fetch(conn, config))

    log.info(f"Totalt {len(new_docs)} nya dokument hittade")

    for doc in new_docs:
        try:
            process_document(doc, conn, analyzers, config, reader)
        except Exception as e:
            log.error(f"Oväntat fel för {doc.get('company')}: {e}", exc_info=True)

    log.info("=== Körning klar ===")


if __name__ == "__main__":
    run()
