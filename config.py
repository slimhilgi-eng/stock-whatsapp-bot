"""
Zentrale Konfiguration – alle Werte werden aus Umgebungsvariablen geladen.
Kopiere .env.example → .env und fülle die Werte aus.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AlphaVantageConfig:
    api_key: str = field(default_factory=lambda: os.getenv("ALPHA_VANTAGE_API_KEY", ""))
    base_url: str = "https://www.alphavantage.co/query"


@dataclass
class WhatsAppConfig:
    # Meta Cloud API
    access_token: str = field(default_factory=lambda: os.getenv("WHATSAPP_ACCESS_TOKEN", ""))
    phone_number_id: str = field(default_factory=lambda: os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""))
    # Ziel: Gruppen-ID oder einzelne Empfänger (kommagetrennt in .env)
    recipient_ids: List[str] = field(
        default_factory=lambda: [
            r.strip()
            for r in os.getenv("WHATSAPP_RECIPIENT_IDS", "").split(",")
            if r.strip()
        ]
    )
    api_version: str = "v19.0"

    @property
    def messages_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"


@dataclass
class WatchlistConfig:
    # Kommagetrennte Ticker in .env, z.B. "AAPL,MSFT,NVDA,TSLA"
    symbols: List[str] = field(
        default_factory=lambda: [
            s.strip().upper()
            for s in os.getenv("WATCHLIST_SYMBOLS", "AAPL,MSFT,NVDA").split(",")
            if s.strip()
        ]
    )


@dataclass
class AlertConfig:
    # Preisänderung in % die einen sofortigen Alert auslöst
    price_change_threshold_pct: float = float(os.getenv("PRICE_ALERT_THRESHOLD_PCT", "3.0"))
    # RSI-Grenzen
    rsi_oversold: float = float(os.getenv("RSI_OVERSOLD", "30"))
    rsi_overbought: float = float(os.getenv("RSI_OVERBOUGHT", "70"))
    # News Sentiment Score Schwelle (-1 bis 1)
    sentiment_bullish_threshold: float = float(os.getenv("SENTIMENT_BULLISH", "0.25"))
    sentiment_bearish_threshold: float = float(os.getenv("SENTIMENT_BEARISH", "-0.25"))


@dataclass
class SchedulerConfig:
    # Tagesbericht um HH:MM Uhr (Lokalzeit des Servers)
    daily_report_time: str = os.getenv("DAILY_REPORT_TIME", "08:00")
    # Wie oft (in Minuten) der Echtzeit-Monitor läuft
    monitor_interval_minutes: int = int(os.getenv("MONITOR_INTERVAL_MIN", "15"))
    # Timezone für den Scheduler
    timezone: str = os.getenv("TZ", "Europe/Berlin")


# Globale Singleton-Instanzen
alpha_vantage = AlphaVantageConfig()
whatsapp = WhatsAppConfig()
watchlist = WatchlistConfig()
alerts = AlertConfig()
scheduler = SchedulerConfig()
