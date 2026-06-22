"""
Empfehlungslogik

Kombiniert technische Indikatoren, Preisalerts und News-Sentiment
zu einer gewichteten BUY / SELL / HOLD-Empfehlung.

Scoring-System (Punkte -3 … +3 je Indikator):
  Positiv (→ BUY) = +1 bis +3
  Negativ (→ SELL) = -1 bis -3
  Neutral          =  0

Gesamt-Score → Signal:
   >= +3  → STRONG BUY  🟢🟢
   +1/+2  → BUY         🟢
   -1/+0  → HOLD        🟡
   -2/-3  → SELL        🔴
   <= -4  → STRONG SELL 🔴🔴
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from alpha_vantage import NewsItem, Quote, TechnicalSignals
import config


class Signal(str, Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG SELL"


SIGNAL_EMOJI = {
    Signal.STRONG_BUY: "🟢🟢",
    Signal.BUY: "🟢",
    Signal.HOLD: "🟡",
    Signal.SELL: "🔴",
    Signal.STRONG_SELL: "🔴🔴",
}


@dataclass
class Recommendation:
    symbol: str
    signal: Signal
    score: int                    # Gesamt-Score
    reasons: List[str]            # Lesbare Begründungen
    is_price_alert: bool = False  # Wurde durch Preisalert ausgelöst?
    quote: Optional[Quote] = None


# ──────────────────────────────────────────────────────────────
# Einzelne Bewertungsfunktionen
# ──────────────────────────────────────────────────────────────

def _score_rsi(rsi: Optional[float], cfg=config.alerts) -> Tuple[int, List[str]]:
    if rsi is None:
        return 0, []
    reasons = [f"RSI: {rsi:.1f}"]
    if rsi <= cfg.rsi_oversold:
        return +2, reasons + ["RSI überverkauft → Kaufsignal"]
    if rsi >= cfg.rsi_overbought:
        return -2, reasons + ["RSI überkauft → Verkaufssignal"]
    if rsi < 45:
        return +1, reasons + ["RSI leicht überverkauft"]
    if rsi > 55:
        return -1, reasons + ["RSI leicht überkauft"]
    return 0, reasons + ["RSI neutral"]


def _score_macd(signals: TechnicalSignals) -> Tuple[int, List[str]]:
    if signals.macd is None or signals.macd_signal is None:
        return 0, []
    reasons = [f"MACD: {signals.macd:.3f} / Signal: {signals.macd_signal:.3f}"]
    hist = signals.macd_hist or 0

    if signals.macd > signals.macd_signal and hist > 0:
        return +2, reasons + ["MACD über Signal-Linie (bullish crossover)"]
    if signals.macd < signals.macd_signal and hist < 0:
        return -2, reasons + ["MACD unter Signal-Linie (bearish crossover)"]
    return 0, reasons + ["MACD neutral"]


def _score_sma(quote: Optional[Quote], signals: TechnicalSignals) -> Tuple[int, List[str]]:
    if quote is None or signals.sma_20 is None or signals.sma_50 is None:
        return 0, []
    price = quote.price
    reasons = [f"SMA20: {signals.sma_20:.2f} | SMA50: {signals.sma_50:.2f}"]

    score = 0
    detail = []
    if price > signals.sma_20:
        score += 1
        detail.append("Kurs über SMA20 ↑")
    else:
        score -= 1
        detail.append("Kurs unter SMA20 ↓")

    if signals.sma_20 > signals.sma_50:
        score += 1
        detail.append("SMA20 > SMA50 (Golden Cross-Trend)")
    else:
        score -= 1
        detail.append("SMA20 < SMA50 (Death Cross-Trend)")

    return score, reasons + detail


def _score_news(news: List[NewsItem], cfg=config.alerts) -> Tuple[int, List[str]]:
    if not news:
        return 0, ["Keine News verfügbar"]

    avg_score = sum(n.sentiment_score for n in news) / len(news)
    reasons = [f"Ø News-Sentiment: {avg_score:+.2f} ({len(news)} Artikel)"]

    if avg_score >= cfg.sentiment_bullish_threshold:
        return +2, reasons + ["News-Sentiment: positiv/bullish"]
    if avg_score <= cfg.sentiment_bearish_threshold:
        return -2, reasons + ["News-Sentiment: negativ/bearish"]
    return 0, reasons + ["News-Sentiment: neutral"]


def _score_price_change(quote: Optional[Quote], cfg=config.alerts) -> Tuple[int, List[str], bool]:
    """Gibt (score, reasons, is_alert) zurück."""
    if quote is None:
        return 0, [], False

    pct = quote.change_pct
    threshold = cfg.price_change_threshold_pct
    reasons = [f"Tagesveränderung: {pct:+.2f}%"]

    if pct >= threshold:
        return +1, reasons + [f"Starker Anstieg (+{pct:.1f}%) ⚡ ALERT"], True
    if pct <= -threshold:
        return -1, reasons + [f"Starker Rückgang ({pct:.1f}%) ⚡ ALERT"], True
    return 0, reasons, False


# ──────────────────────────────────────────────────────────────
# Haupt-Empfehlung
# ──────────────────────────────────────────────────────────────

def _score_to_signal(score: int) -> Signal:
    if score >= 4:
        return Signal.STRONG_BUY
    if score >= 2:
        return Signal.BUY
    if score >= -1:
        return Signal.HOLD
    if score >= -3:
        return Signal.SELL
    return Signal.STRONG_SELL


def generate_recommendation(
    quote: Optional[Quote],
    tech: TechnicalSignals,
    news: List[NewsItem],
) -> Recommendation:
    """Kombiniert alle Scores zur finalen Empfehlung."""

    all_reasons: List[str] = []
    total_score = 0

    rsi_score, rsi_reasons = _score_rsi(tech.rsi)
    total_score += rsi_score
    all_reasons.extend(rsi_reasons)

    macd_score, macd_reasons = _score_macd(tech)
    total_score += macd_score
    all_reasons.extend(macd_reasons)

    sma_score, sma_reasons = _score_sma(quote, tech)
    total_score += sma_score
    all_reasons.extend(sma_reasons)

    news_score, news_reasons = _score_news(news)
    total_score += news_score
    all_reasons.extend(news_reasons)

    price_score, price_reasons, is_alert = _score_price_change(quote)
    total_score += price_score
    all_reasons.extend(price_reasons)

    signal = _score_to_signal(total_score)

    return Recommendation(
        symbol=tech.symbol,
        signal=signal,
        score=total_score,
        reasons=all_reasons,
        is_price_alert=is_alert,
        quote=quote,
    )


# ──────────────────────────────────────────────────────────────
# Nachrichtenformatierung
# ──────────────────────────────────────────────────────────────

def format_recommendation_message(rec: Recommendation, news: List[NewsItem]) -> str:
    """Erstellt die WhatsApp-Nachricht für eine Empfehlung."""
    emoji = SIGNAL_EMOJI[rec.signal]
    lines = [
        f"{'⚡ ALERT ' if rec.is_price_alert else ''}📊 *{rec.symbol}*",
        f"{emoji} *{rec.signal.value}* (Score: {rec.score:+d})",
    ]

    if rec.quote:
        q = rec.quote
        arrow = "▲" if q.change >= 0 else "▼"
        lines.append(
            f"Kurs: ${q.price:.2f}  {arrow} {q.change:+.2f} ({q.change_pct:+.2f}%)"
        )

    lines.append("")
    lines.append("*Begründung:*")
    for reason in rec.reasons:
        lines.append(f"• {reason}")

    if news:
        lines.append("")
        lines.append("*Aktuelle News:*")
        for item in news[:3]:
            sentiment_icon = "🟢" if item.sentiment_score > 0 else ("🔴" if item.sentiment_score < 0 else "🟡")
            lines.append(f"{sentiment_icon} {item.title[:80]}…")
            lines.append(f"   {item.url}")

    return "\n".join(lines)


def format_daily_report(recommendations: List[Recommendation]) -> str:
    """Fasst alle Empfehlungen zum Tagesbericht zusammen."""
    from datetime import date
    today = date.today().strftime("%d.%m.%Y")

    lines = [
        f"📈 *Aktien-Tagesbericht – {today}*",
        "─" * 30,
    ]

    # Sortiert nach Score (bestes zuerst)
    for rec in sorted(recommendations, key=lambda r: r.score, reverse=True):
        emoji = SIGNAL_EMOJI[rec.signal]
        price_str = f"${rec.quote.price:.2f}" if rec.quote else "N/A"
        change_str = (
            f"({rec.quote.change_pct:+.2f}%)" if rec.quote else ""
        )
        lines.append(f"{emoji} *{rec.symbol}* – {rec.signal.value}")
        lines.append(f"   Kurs: {price_str} {change_str}")

    lines.append("─" * 30)
    lines.append("_Daten: Alpha Vantage | Kein Anlageberatung_")
    return "\n".join(lines)
