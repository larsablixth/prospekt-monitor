"""
notifier.py — Skickar e-postnotis med analysresultat.

Bygger en tydlig HTML-e-post med konsensuspoäng, per-provider-resultat
och röda/gröna flaggor.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

VERDICT_EMOJI = {
    "Gå vidare": "✅",
    "Tveksamt":  "⚠️",
    "Undvik":    "❌",
}

VERDICT_COLOR = {
    "Gå vidare": "#2e7d32",
    "Tveksamt":  "#e65100",
    "Undvik":    "#c62828",
}


def _consensus(analyses: list) -> dict:
    """Beräknar konsensuspoäng och majoritetsverdict."""
    scores   = [a["total_score"] for a in analyses if "total_score" in a]
    verdicts = [a["verdict"] for a in analyses if "verdict" in a]
    avg_score = int(sum(scores) / len(scores)) if scores else 0
    verdict = max(set(verdicts), key=verdicts.count) if verdicts else "Okänt"
    return {"score": avg_score, "verdict": verdict}


def _build_html(doc: dict, analyses: list) -> str:
    company  = doc.get("company", "Okänt bolag")
    source   = doc.get("source", "")
    cons     = _consensus(analyses)
    v_emoji  = VERDICT_EMOJI.get(cons["verdict"], "")
    v_color  = VERDICT_COLOR.get(cons["verdict"], "#333")

    # Provider-tabeller
    provider_html = ""
    for a in analyses:
        provider = a.get("provider", "?")
        score    = a.get("score", "–")
        verdict  = a.get("verdict", "–")
        summary  = a.get("summary", "")
        full     = a.get("full_result", {})

        cats_html = ""
        for cat, val in (full.get("categories") or {}).items():
            cats_html += f"<tr><td style='padding:2px 8px'>{cat}</td><td style='padding:2px 8px'><b>{val.get('score','?')}</b></td><td style='padding:2px 8px;color:#555'>{val.get('comment','')}</td></tr>"

        flags_html = ""
        for flag in (full.get("red_flags") or []):
            flags_html += f"<li style='color:#c62828'>🚩 {flag}</li>"
        for flag in (full.get("green_flags") or []):
            flags_html += f"<li style='color:#2e7d32'>✅ {flag}</li>"

        provider_html += f"""
        <div style='border:1px solid #ddd;border-radius:6px;padding:16px;margin-bottom:16px'>
          <h3 style='margin:0 0 8px'>{provider.upper()} — {score}p
            <span style='color:{VERDICT_COLOR.get(verdict,"#333")};font-size:0.9em'> {VERDICT_EMOJI.get(verdict,'')} {verdict}</span>
          </h3>
          <p style='color:#444;margin:4px 0'>{summary}</p>
          {f'<table style="margin:8px 0;font-size:0.9em">{cats_html}</table>' if cats_html else ''}
          {f'<ul style="margin:8px 0;font-size:0.9em">{flags_html}</ul>' if flags_html else ''}
        </div>"""

    return f"""
    <html><body style='font-family:sans-serif;max-width:800px;margin:auto;padding:20px'>
      <h1 style='border-bottom:2px solid #ccc;padding-bottom:8px'>
        Nytt prospekt: {company}
      </h1>
      <p style='color:#666'>Källa: {source} &nbsp;|&nbsp; Dokument-ID: {doc.get("id","")}</p>

      <div style='background:#f5f5f5;border-radius:8px;padding:20px;margin:16px 0;text-align:center'>
        <div style='font-size:2em;font-weight:bold;color:{v_color}'>{v_emoji} {cons["verdict"]}</div>
        <div style='font-size:1.4em;color:#333'>Konsensuspoäng: {cons["score"]}/100</div>
      </div>

      <h2>Analys per AI-provider</h2>
      {provider_html}

      <hr style='margin-top:32px'>
      <p style='color:#999;font-size:0.85em'>
        PDF: {doc.get("local_path") or doc.get("url","–")}<br>
        Prospekt Monitor — automatisk analys
      </p>
    </body></html>"""


def send(doc: dict, analyses: list, config: dict):
    """Skickar e-postnotis. analyses = lista med dicts från DB."""
    company = doc.get("company", "Okänt bolag")
    cons    = _consensus(analyses)

    # Kontrollera min_score
    min_score = config.get("analysis", {}).get("min_score_to_notify", 0)
    if cons["score"] < min_score:
        log.info(f"Notis hoppas över för {company} (score {cons['score']} < {min_score})")
        return

    subject = f"{VERDICT_EMOJI.get(cons['verdict'], '')} Nytt prospekt: {company} — {cons['score']}p ({cons['verdict']})"
    html    = _build_html(doc, analyses)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config["email"]["from_addr"]
    msg["To"]      = ", ".join(config["email"]["to_addrs"])
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(config["email"]["smtp_host"], config["email"]["smtp_port"]) as smtp:
            smtp.starttls()
            smtp.login(config["email"]["username"], config["email"]["password"])
            smtp.sendmail(
                config["email"]["from_addr"],
                config["email"]["to_addrs"],
                msg.as_string(),
            )
        log.info(f"E-post skickad för {company}")
    except Exception as e:
        log.error(f"E-postfel för {company}: {e}")
