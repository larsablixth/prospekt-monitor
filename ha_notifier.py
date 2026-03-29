"""
ha_notifier.py — Skickar notiser till Home Assistant.

Två kanaler:
  1. REST API  → push-notis direkt till mobilen via HA Companion-appen
  2. Webhook   → triggar en HA-automation som kan göra vad som helst

Båda är konfigurerbara och körs parallellt om båda är uppsatta.
"""

import logging
import requests

log = logging.getLogger(__name__)

VERDICT_EMOJI = {
    "Gå vidare": "✅",
    "Tveksamt":  "⚠️",
    "Undvik":    "❌",
}


def _consensus(analyses: list) -> dict:
    scores  = [a["score"] for a in analyses if a.get("score") is not None]
    verdicts = [a["verdict"] for a in analyses if a.get("verdict")]
    avg_score = int(sum(scores) / len(scores)) if scores else 0
    verdict   = max(set(verdicts), key=verdicts.count) if verdicts else "Okänt"
    return {"score": avg_score, "verdict": verdict}


def _build_notification(doc: dict, analyses: list) -> dict:
    """Bygger notis-payload för HA Companion push."""
    company = doc.get("company", "Okänt bolag")
    cons    = _consensus(analyses)
    emoji   = VERDICT_EMOJI.get(cons["verdict"], "")

    # Samla röda flaggor från alla providers
    red_flags = []
    for a in analyses:
        full = a.get("full_result", {})
        for flag in (full.get("red_flags") or [])[:2]:  # max 2 per provider
            if flag not in red_flags:
                red_flags.append(flag)

    # Bygg notistext — kompakt för mobilskärm
    body_lines = [f"Poäng: {cons['score']}/100 — {cons['verdict']}"]
    for flag in red_flags[:3]:  # max 3 flaggor i notisen
        body_lines.append(f"🚩 {flag[:80]}")  # trunkera långa flaggor

    return {
        "title": f"{emoji} Nytt prospekt: {company}",
        "message": "\n".join(body_lines),
        "data": {
            "tag": f"prospekt_{doc.get('id', '')}",
            "group": "prospekt-monitor",
            "color": (
                "#2e7d32" if cons["verdict"] == "Gå vidare" else
                "#e65100" if cons["verdict"] == "Tveksamt"  else
                "#c62828"
            ),
            # Action-knapp som öppnar PDF-URL eller Avanza-sida
            "actions": [
                {
                    "action": "URI",
                    "title": "Öppna prospekt",
                    "uri": doc.get("url", "https://www.fi.se/sv/vara-register/prospektregistret/"),
                }
            ],
        },
    }


def _build_webhook_payload(doc: dict, analyses: list) -> dict:
    """Bygger payload för HA webhook — fullständig data för automationer."""
    cons = _consensus(analyses)

    red_flags = []
    for a in analyses:
        full = a.get("full_result", {})
        red_flags.extend(full.get("red_flags") or [])

    return {
        "company":    doc.get("company"),
        "source":     doc.get("source"),
        "doc_id":     doc.get("id"),
        "url":        doc.get("url"),
        "score":      cons["score"],
        "verdict":    cons["verdict"],
        "red_flags":  list(dict.fromkeys(red_flags))[:5],  # unika, max 5
        "providers":  [
            {
                "name":    a.get("provider"),
                "score":   a.get("score"),
                "verdict": a.get("verdict"),
            }
            for a in analyses
        ],
    }


def send_rest(doc: dict, analyses: list, config: dict):
    """Skickar push-notis via HA REST API → Companion-appen."""
    ha_cfg   = config.get("home_assistant", {})
    base_url = ha_cfg.get("url", "").rstrip("/")
    token    = ha_cfg.get("token", "")
    app      = ha_cfg.get("mobile_app", "")

    if not all([base_url, token, app]):
        log.debug("HA REST: konfiguration saknas, hoppar över")
        return

    url     = f"{base_url}/api/services/notify/mobile_app_{app}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    payload = _build_notification(doc, analyses)

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        log.info(f"HA REST: notis skickad för {doc.get('company')}")
    except requests.exceptions.HTTPError as e:
        log.error(f"HA REST: HTTP-fel {e.response.status_code} — kontrollera token och enhetnamn")
    except Exception as e:
        log.error(f"HA REST: fel vid notis: {e}")


def send_webhook(doc: dict, analyses: list, config: dict):
    """POSTar fullständig data till HA webhook."""
    ha_cfg     = config.get("home_assistant", {})
    base_url   = ha_cfg.get("url", "").rstrip("/")
    webhook_id = ha_cfg.get("webhook_id", "")

    if not all([base_url, webhook_id]):
        log.debug("HA Webhook: konfiguration saknas, hoppar över")
        return

    url     = f"{base_url}/api/webhook/{webhook_id}"
    payload = _build_webhook_payload(doc, analyses)

    try:
        r = requests.post(url, json=payload, timeout=10)
        # HA webhooks returnerar 200 eller 202 även utan automation
        log.info(f"HA Webhook: payload skickad för {doc.get('company')} (status {r.status_code})")
    except Exception as e:
        log.error(f"HA Webhook: fel: {e}")


def send(doc: dict, analyses: list, config: dict):
    """Kör båda kanalerna."""
    send_rest(doc, analyses, config)
    send_webhook(doc, analyses, config)
