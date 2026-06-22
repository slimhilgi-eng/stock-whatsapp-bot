# Stock WhatsApp Bot – Setup-Anleitung

## Architektur-Übersicht

```
Alpha Vantage API
  ├── Kursdaten (GLOBAL_QUOTE)
  ├── RSI / MACD / SMA (Technical Indicators)
  └── News Sentiment
          ↓
    signals.py  ←  Scoring-Logik  →  BUY / SELL / HOLD
          ↓
    whatsapp.py  →  Meta Cloud API  →  WhatsApp-Empfänger
          ↓
    main.py / APScheduler
      ├── Tagesbericht (täglich 08:00)
      └── Echtzeit-Monitor (alle 15 Min)
```

---

## Schritt 1: Alpha Vantage API-Key

1. Kostenlos unter https://www.alphavantage.co/support/#api-key registrieren
2. Key in `.env` eintragen: `ALPHA_VANTAGE_API_KEY=DEIN_KEY`

**Limits Free Tier:** 25 Requests/Tag, 5 Requests/Minute  
→ Der Bot wartet automatisch zwischen Requests (12 Sekunden).  
→ Für mehr Symbole: Premium-Plan ab $50/Monat empfohlen.

---

## Schritt 2: Meta WhatsApp Business API

### 2a. Meta Developer Account

1. https://developers.facebook.com → "Meine Apps" → "App erstellen"
2. App-Typ: **Business**
3. Produkt hinzufügen: **WhatsApp**

### 2b. Test-Nummer einrichten

1. Im Dashboard: **WhatsApp → Getting Started**
2. Dort findest du:
   - **Temporärer Access Token** (24h gültig) → `WHATSAPP_ACCESS_TOKEN`
   - **Phone Number ID** → `WHATSAPP_PHONE_NUMBER_ID`
3. "Zu einer Nummer hinzufügen" → Deine eigene Nummer verifizieren

### 2c. Empfänger freischalten (Testphase)

Im Meta-Dashboard können bis zu 5 Test-Empfänger eingetragen werden.  
Jeder muss einmalig dem Bot eine Nachricht senden, um das 24h-Nachrichtenfenster zu öffnen.

**Für den produktiven Betrieb:**
- Permanenten System-User-Token erzeugen (nie abläuft):  
  Business Manager → Einstellungen → System-User → Token generieren
- Business-Verifizierung bei Meta abschließen (für unbegrenzte Empfänger)

### 2d. Webhook (optional, für eingehende Nachrichten)

Falls du auf Nachrichten reagieren möchtest (z.B. "/status AAPL"):
1. Einen HTTP-Server exponieren (z.B. via ngrok für lokale Tests)
2. In Meta Dashboard: Webhook-URL + Verify-Token eintragen
3. `WhatsAppClient.verify_webhook()` in deine Flask/FastAPI-Route einbauen

---

## Schritt 3: Installation

```bash
# Python 3.10+ vorausgesetzt
cd stock_whatsapp_bot

# Virtuelle Umgebung (empfohlen)
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Abhängigkeiten
pip install -r requirements.txt

# .env konfigurieren
cp .env.example .env
# → .env mit deinen API-Keys und Empfängernummern befüllen
```

---

## Schritt 4: Testen

```bash
# 1. Testnachricht senden (prüft WhatsApp-Verbindung)
python main.py --test

# 2. Einmaligen Tagesbericht generieren
python main.py --once

# 3. Einmaligen Echtzeit-Monitor laufen lassen
python main.py --alert

# 4. Bot als Daemon starten
python main.py
```

---

## Schritt 5: Produktiv-Deployment (Server)

### Option A: Systemd-Service (Linux VPS)

```ini
# /etc/systemd/system/stockbot.service
[Unit]
Description=Stock WhatsApp Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/stock_whatsapp_bot
EnvironmentFile=/opt/stock_whatsapp_bot/.env
ExecStart=/opt/stock_whatsapp_bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable stockbot
sudo systemctl start stockbot
sudo journalctl -u stockbot -f  # Logs
```

### Option B: Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker build -t stockbot .
docker run -d --env-file .env --name stockbot stockbot
```

---

## Empfehlungslogik (Scoring)

| Indikator       | Kaufsignal (+)              | Verkaufssignal (-)           |
|-----------------|----------------------------|------------------------------|
| RSI             | RSI < 30 (überverkauft)    | RSI > 70 (überkauft)         |
| MACD            | MACD über Signal-Linie     | MACD unter Signal-Linie      |
| SMA             | Kurs > SMA20, SMA20 > SMA50| Kurs < SMA20, SMA20 < SMA50  |
| News Sentiment  | Ø Score > 0.25             | Ø Score < -0.25              |
| Preisänderung   | > +3% (Alert)              | < -3% (Alert)                |

**Gesamt-Score → Signal:**
- ≥ +4 → STRONG BUY 🟢🟢
- +2/+3 → BUY 🟢
- -1 bis +1 → HOLD 🟡
- -2/-3 → SELL 🔴
- ≤ -4 → STRONG SELL 🔴🔴

---

## Wichtige Hinweise

- **Kein Anlageberatung:** Dieses Tool ist rein informativ.
- **WhatsApp Gruppen:** Die Meta Cloud API unterstützt keine direkten Gruppen-Nachrichten.
  Nachrichten werden an Einzelnummern gesendet. Empfänger können sich dann selbst
  in einer Gruppe organisieren, in die sie die Infos weiterleiten.
- **Rate Limits:** Bei vielen Symbolen (>5) Premium Alpha Vantage empfohlen.
- **Compliance:** WhatsApp Business Policy beachten – keine Spam-Nachrichten.
