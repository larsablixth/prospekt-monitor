# Prospekt Monitor

Bevakar automatiskt tre källor för nya svenska börsnoteringar, laddar hem prospekt-PDF:er till Google Drive, analyserar nyckelavsnitt med tre AI-modeller och skickar notiser via e-post och Home Assistant.

## Datakällor

| Källa | Metod | Täcker |
|---|---|---|
| FI Prospektregistret | HTML-scraping | Alla FI-godkända aktieprospekt |
| Nasdaq RSS | Officiella RSS-flöden | First North + Main Market notices |
| Avanza | Publik JSON-endpoint | IPO:er där Avanza är selling agent |

## Analysmodell

Sex kategorier, 100 poäng totalt:

| Kategori | Max poäng |
|---|---|
| Finansiell hälsa | 25 |
| Ägarstruktur | 20 |
| Affärsmodell | 20 |
| Ledning & styrelse | 15 |
| Prospektkvalitet | 10 |
| Marknad & timing | 10 |

- **70–100** ✅ Gå vidare
- **40–69**  ⚠️ Tveksamt
- **0–39**   ❌ Undvik

Tre AI-providers analyserar varje prospekt parallellt och ett konsensuspoäng beräknas.

## Infrastruktur

- **Körmiljö:** LXC-container i Proxmox (Debian 12, 1 core, 512 MB RAM, 8 GB disk)
- **Schemaläggning:** systemd timer, var 6:e timme
- **PDF-lagring:** Google Drive via rclone
- **Databas:** SQLite (lokal, deduplicering)

## Notifikationer

- **E-post** — fullständig HTML-rapport med poäng, motiveringar och citat per AI-provider
- **Home Assistant REST API** — push-notis till Companion-appen på mobilen
- **Home Assistant Webhook** — triggar automation för persistent notis i dashboard

## Installation

Se `docs/Prospekt_Monitor_Installationsmanual.docx` för fullständig steg-för-steg-guide inkl. Proxmox-setup och Google Drive med rclone.

```bash
# 1. Klona repot
git clone https://github.com/DITT_REPO/prospekt-monitor.git
cd prospekt-monitor

# 2. Skapa virtualenv och installera beroenden
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Konfigurera
cp config.example.yaml config.yaml
# Redigera config.yaml — API-nycklar, e-post och Home Assistant

# 4. Testa manuellt
python prospekt_monitor.py

# 5. Installera systemd timer
sudo cp systemd/prospekt-monitor.service /etc/systemd/system/
sudo cp systemd/prospekt-monitor.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now prospekt-monitor.timer
```

## Konfiguration

Se `config.example.yaml`. Viktigt:
- `config.yaml` committas **aldrig** — finns i `.gitignore`
- Varje AI-provider aktiveras/avaktiveras med `enabled: true/false`
- `min_score_to_notify` styr minsta poäng för notis (0 = skicka alltid)
- `storage.download_dir` ska peka på rclone-mountad Google Drive-mapp

## Filstruktur

```
prospekt-monitor/
├── prospekt_monitor.py     # Huvudskript — orkestrerar allt
├── db.py                   # SQLite-hantering och deduplicering
├── pdf_extractor.py        # Extraherar 5 nyckelavsnitt ur PDF
├── notifier.py             # E-postnotis med HTML-rapport
├── ha_notifier.py          # Home Assistant REST API + Webhook
├── scrapers/
│   ├── fi.py               # FI Prospektregistret (HTML-scraping)
│   ├── nasdaq_rss.py       # Nasdaq officiella RSS-flöden
│   └── avanza.py           # Avanzas publika erbjudande-API
├── analyzer/
│   ├── base.py             # Gemensamt interface + analyseprompt
│   ├── claude.py           # Anthropic Claude
│   ├── openai.py           # OpenAI GPT-4o
│   └── gemini.py           # Google Gemini
├── home_assistant/
│   └── automation_prospekt.yaml  # HA automation-mall
├── systemd/
│   ├── prospekt-monitor.service
│   └── prospekt-monitor.timer
├── docs/
│   └── Prospekt_Monitor_Installationsmanual.docx
├── config.example.yaml     # Konfigurationsmall (committas)
├── config.yaml             # Din konfiguration (committas ALDRIG)
├── requirements.txt
└── .gitignore
```

## API-nycklar som behövs

| Nyckel | Hämtas från |
|---|---|
| Anthropic Claude | console.anthropic.com |
| OpenAI | platform.openai.com |
| Google Gemini | aistudio.google.com |
| Gmail App Password | myaccount.google.com → Säkerhet → App-lösenord |
| HA Long-Lived Token | HA → Profil → Säkerhet → Åtkomsttokens |
