"""
scrapers/avanza.py — Hämtar aktiva IPO-erbjudanden från Avanzas publika API.

Använder den odokumenterade men publika endpoint som driver sidan
avanza.se/borsintroduktioner-emissioner.html — ingen inloggning krävs.

OBS: Avanza har inget officiellt API. Denna endpoint kan förändras
utan förvarning. Vid fel loggas ett varningsmeddelande och tom lista returneras.
"""

import hashlib
import logging

import requests

# Publik endpoint — hämtar alla aktiva erbjudanden (IPO, nyemission, uppköp)
OFFERS_URL = "https://www.avanza.se/ab/emptyguid/offers"

# Vi är bara intresserade av börsintroduktioner och nyemissioner
WANTED_OFFER_TYPES = {
    "IPO",                  # Börsintroduktion
    "EQUITY_OFFER",         # Nyemission
    "NEW_LISTING",          # Direktnotering
    "INTRODUCTION",         # Alternativ beteckning
}

log = logging.getLogger(__name__)


def _doc_id(offer_id: str) -> str:
    return "avanza_" + hashlib.md5(str(offer_id).encode()).hexdigest()[:12]


def fetch_new(conn, config: dict) -> list[dict]:
    """
    Returnerar lista med nya IPO-erbjudanden från Avanza.
    Dessa har ingen PDF-URL — url pekar på Avanzas erbjudandesida.
    """
    from db import is_new

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.avanza.se/borsintroduktioner-emissioner.html",
    })

    try:
        r = session.get(OFFERS_URL, timeout=20)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        log.warning(f"Avanza: HTTP-fel {e.response.status_code} — endpoint kanske ändrats")
        return []
    except Exception as e:
        log.warning(f"Avanza: kunde inte hämta erbjudanden: {e}")
        return []

    # Datan kan vara en lista direkt eller nästlad under en nyckel
    offers = data if isinstance(data, list) else data.get("offers", data.get("items", []))

    if not offers:
        log.debug("Avanza: inga erbjudanden hittades")
        return []

    new_docs = []
    for offer in offers:
        offer_type = str(offer.get("offerType", offer.get("type", ""))).upper()

        # Filtrera — ta bara IPO och nyemissioner
        if not any(t in offer_type for t in WANTED_OFFER_TYPES):
            # Försök även matcha på namn/beskrivning om typ saknas
            name = str(offer.get("name", "")).lower()
            desc = str(offer.get("description", "")).lower()
            if not any(kw in name + desc for kw in ["introduktion", "ipo", "notering", "emission"]):
                continue

        offer_id = offer.get("id", offer.get("offerId", ""))
        if not offer_id:
            continue

        doc_id = _doc_id(offer_id)
        if not is_new(conn, doc_id):
            continue

        company = (
            offer.get("issuerName") or
            offer.get("companyName") or
            offer.get("name") or
            "Okänt bolag"
        )

        # Bygg länk till Avanzas erbjudandesida
        offer_url = offer.get("url") or f"https://www.avanza.se/borsintroduktioner-emissioner.html"

        log.info(f"Avanza: nytt erbjudande — {company} ({offer_type})")
        new_docs.append({
            "id":         doc_id,
            "source":     "Avanza",
            "company":    company,
            "doc_type":   offer_type.lower() or "ipo",
            "url":        offer_url,
            "local_path": None,
        })

    return new_docs
