"""
scrapers/fi.py — Scraper för FI:s prospektregister.

Hämtar listsidan, filtrerar på aktier + prospekt/EU-tillväxtprospekt,
och returnerar nya dokument med PDF-URL.
"""

import hashlib
import logging
import re

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fi.se"
LIST_URL = "https://www.fi.se/sv/vara-register/prospektregistret/"
DETAIL_URL = "https://www.fi.se/sv/vara-register/prospektregistret/details"

# Vi vill bara ha aktie-prospekt, inte obligationer/derivat
WANTED_SECURITIES = {"aktier", "depåbevis", "konvertibel"}
WANTED_DOC_TYPES  = {"prospekt", "eu-tillväxtprospekt", "förenklat prospekt"}

log = logging.getLogger(__name__)


def _doc_id(fi_id: str) -> str:
    return f"fi_{fi_id}"


def _fetch_pdf_url(fi_id: str, session: requests.Session) -> str | None:
    """Hämtar detaljsidan och extraherar direktlänken till PDF."""
    try:
        r = session.get(DETAIL_URL, params={"id": fi_id}, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if "GetFile" in a["href"] and "pdf" in a["href"].lower():
                href = a["href"]
                return href if href.startswith("http") else BASE_URL + href
    except Exception as e:
        log.warning(f"FI: kunde inte hämta detaljsida för {fi_id}: {e}")
    return None


def fetch_new(conn, config: dict) -> list[dict]:
    """
    Returnerar lista med nya dokument (ej i DB sedan tidigare).
    Varje post: id, source, company, doc_type, url, local_path=None
    """
    session = requests.Session()
    session.headers["User-Agent"] = "ProspektMonitor/1.0"

    try:
        r = session.get(LIST_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log.error(f"FI: kunde inte hämta listsida: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("FI: hittade ingen tabell på sidan")
        return []

    new_docs = []
    for row in table.find_all("tr")[1:]:   # hoppa över header
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        date_text    = cols[0].get_text(strip=True)
        company      = cols[1].get_text(strip=True)
        security     = cols[2].get_text(strip=True).lower()
        doc_link     = cols[3].find("a")

        if not doc_link:
            continue

        doc_type = doc_link.get_text(strip=True).lower()

        # Filtrera — vi vill bara ha aktier och rätt dokumenttyp
        if not any(w in security for w in WANTED_SECURITIES):
            continue
        if not any(w in doc_type for w in WANTED_DOC_TYPES):
            continue

        # Extrahera FI-ärendenummer från länkens href
        href = doc_link.get("href", "")
        match = re.search(r"id=([\w-]+)", href)
        if not match:
            continue
        fi_id = match.group(1)
        doc_id = _doc_id(fi_id)

        # Kolla mot DB
        from db import is_new
        if not is_new(conn, doc_id):
            continue

        # Hämta PDF-URL från detaljsidan
        pdf_url = _fetch_pdf_url(fi_id, session)
        if not pdf_url:
            log.warning(f"FI: ingen PDF-URL hittad för {company} ({fi_id})")
            continue

        log.info(f"FI: nytt prospekt — {company} ({date_text})")
        new_docs.append({
            "id":         doc_id,
            "source":     "FI",
            "company":    company,
            "doc_type":   doc_type,
            "url":        pdf_url,
            "local_path": None,
        })

    return new_docs
