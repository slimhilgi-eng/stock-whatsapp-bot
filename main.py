"""
Stock-WhatsApp-Bot – Einstiegspunkt

Zwei Betriebsmodi:
  python main.py          → Startet den Scheduler (Daemon)
  python main.py --once   → Führt einmalig den Tagesbericht aus (zum Testen)
  python main.py --alert  → Führt einmalig den Echtzeit-Monitor aus
"""

import argparse
import logging
import time
from typing import List

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import config
from alpha_vantage import AlphaVantageClient
from signals import (
    generate_recommendation,
    format_recommendation_message,
    format_daily_report,
    Signal,
    Recommendation,
)
from whatsapp import WhatsAppClient

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

# ── Clients ─────────────────────────────────────────────────────
av_client = AlphaVantageClient()
wa_client = WhatsAppClient()

# Einfacher In-Memory-Cache: Letzter bekannter Kurs je Symbol
_last_prices: dict = {}


# ──────────────────────────────────────────────────────────────
# Jobs
# ──────────────────────────────────────────────────────────────

def run_daily_report() -> None:
    """Tagesbericht: alle Symbole analysieren und zusammenfassen."""
    logger.info("=== Tagesbericht gestartet ===")
    symbols = config.watchlist.symbols
    recommendations: List[Recommendation] = []

    for symbol in symbols:
        logger.info("Analysiere %s...", symbol)
        try:
            quote, tech, news = av_client.get_all_data(symbol)
            rec = generate_recommendation(quote, tech, news)
            recommendations.append(rec)
            time.sleep(12)  # Rate-Limit-Puffer
        except Exception as e:
            logger.error("Fehler bei %s: %s", symbol, e)

    if not recommendations:
        logger.warning("Keine Daten für Tagesbericht.")
        return

    # Zusammenfassung senden
    summary = format_daily_report(recommendations)
    sent = wa_client.broadcast(summary)
    logger.info("Tagesbericht gesendet an %d Empfänger.", sent)

    # Detailnachricht nur für starke Signale
    for rec in recommendations:
        if rec.signal in (Signal.STRONG_BUY, Signal.STRONG_SELL):
            detail = format_recommendation_message(rec, [])
            wa_client.broadcast(detail)
            time.sleep(2)

    logger.info("=== Tagesbericht abgeschlossen ===")


def run_realtime_monitor() -> None:
    """Echtzeit-Monitor: Preisalerts und starke Signale sofort melden."""
    logger.info("--- Echtzeit-Monitor läuft ---")
    symbols = config.watchlist.symbols

    for symbol in symbols:
        try:
            quote = av_client.get_quote(symbol)
            if quote is None:
                continue

            # Preisalert-Prüfung
            threshold = config.alerts.price_change_threshold_pct
            if abs(quote.change_pct) >= threshold:
                logger.info("PREISALERT: %s  %+.2f%%", symbol, quote.change_pct)

                # Vollständige Analyse nur bei Alert
                _, tech, news = av_client.get_all_data(symbol)
                rec = generate_recommendation(quote, tech, news)
                msg = format_recommendation_message(rec, news)
                wa_client.broadcast(msg)

            time.sleep(12)  # Rate-Limit

        except Exception as e:
            logger.error("Monitor-Fehler bei %s: %s", symbol, e)


# ──────────────────────────────────────────────────────────────
# Scheduler-Setup
# ──────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone=config.scheduler.timezone)

    # Tagesbericht
    hour, minute = config.scheduler.daily_report_time.split(":")
    scheduler.add_job(
        run_daily_report,
        CronTrigger(
            hour=int(hour),
            minute=int(minute),
            timezone=config.scheduler.timezone,
        ),
        id="daily_report",
        name="Täglicher Aktien-Bericht",
        misfire_grace_time=300,
    )
    logger.info("Tagesbericht geplant für %s Uhr (%s).",
                config.scheduler.daily_report_time, config.scheduler.timezone)

    # Echtzeit-Monitor
    interval = config.scheduler.monitor_interval_minutes
    scheduler.add_job(
        run_realtime_monitor,
        IntervalTrigger(minutes=interval),
        id="realtime_monitor",
        name="Echtzeit-Preismonitor",
        misfire_grace_time=60,
    )
    logger.info("Echtzeit-Monitor gestartet (alle %d Min).", interval)

    logger.info("Bot läuft. Strg+C zum Beenden.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Bot gestoppt.")


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Stock WhatsApp Bot")
    parser.add_argument("--once", action="store_true", help="Einmalig Tagesbericht senden")
    parser.add_argument("--alert", action="store_true", help="Einmalig Monitor-Lauf")
    parser.add_argument("--test", action="store_true", help="Testnachricht senden")
    args = parser.parse_args()

    # Konfiguration validieren
    if not config.alpha_vantage.api_key:
        logger.error("ALPHA_VANTAGE_API_KEY nicht gesetzt!")
        return
    if not config.whatsapp.access_token:
        logger.error("WHATSAPP_ACCESS_TOKEN nicht gesetzt!")
        return
    if not config.whatsapp.recipient_ids:
        logger.error("WHATSAPP_RECIPIENT_IDS nicht gesetzt!")
        return

    if args.test:
        sent = wa_client.broadcast("🤖 Stock-Bot läuft erfolgreich! Testnachricht.")
        logger.info("Testnachricht an %d Empfänger gesendet.", sent)
    elif args.once:
        run_daily_report()
    elif args.alert:
        run_realtime_monitor()
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
