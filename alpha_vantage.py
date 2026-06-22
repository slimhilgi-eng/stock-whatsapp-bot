"""
Alpha Vantage API-Client

Stellt folgende Daten bereit:
  - Echtzeit-Kurs (GLOBAL_QUOTE)
  - RSI, MACD, SMA (Technical Indicators)
  - News & Sentiment (NEWS_SENTIMENT)
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

import config

logger = logging.getLogger(__name__)

# Alpha Vantage Free Tier: 25 Requests/Tag, 5 Requests/Min
_REQUEST_DELAY = 12.5  # Sekunden zwischen Requests (5/min = 1 pro 12s)


@dataclass
class Quote:
    symbol: str
    price: float
    change: float
    change_pct: float
    volume: int
    latest_trading_day: str


@dataclass
class TechnicalSignals:
    symbol: str
    rsi: Optional[float]         # 14-Tage RSI
    macd: Optional[float]        # MACD-Linie
    macd_signal: Optional[float] # Signal-Linie
    macd_hist: Optional[float]   # Histogramm
    sma_20: Optional[float]      # 20-Tage SMA
    sma_50: Optional[float]      # 50-Tage SMA


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    sentiment_score: float       # -1 (sehr bearish) bis +1 (sehr bullish)
    sentiment_label: str


class AlphaVantageClient:
    def __init__(self):
        self.api_key = config.alpha_vantage.api_key
        self.base_url = config.alpha_vantage.base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "StockBot/1.0"})

    def _get(self, params: Dict) -> Optional[Dict]:
        """HTTP GET mit Retry-Logik."""
        params["apikey"] = self.api_key
        for attempt in range(3):
            try:
                resp = self.session.get(self.base_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if "Note" in data:
                    logger.warning("Alpha Vantage API-Limit erreicht. Warte 60s...")
                    time.sleep(60)
                    continue
                if "Error Message" in data:
                    logger.error("Alpha Vantage Fehler: %s", data["Error Message"])
                    return None
                return data
            except requests.RequestException as e:
                logger.error("Request-Fehler (Versuch %d/3): %s", attempt + 1, e)
                time.sleep(5)
        return None

    # ──────────────────────────────────────────────────────────
    # Kursdaten
    # ──────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Aktueller Kurs via GLOBAL_QUOTE."""
        data = self._get({"function": "GLOBAL_QUOTE", "symbol": symbol})
        if not data:
            return None
        q = data.get("Global Quote", {})
        if not q or "05. price" not in q:
            logger.warning("Keine Kursdaten für %s", symbol)
            return None
        try:
            return Quote(
                symbol=symbol,
                price=float(q["05. price"]),
                change=float(q["09. change"]),
                change_pct=float(q["10. change percent"].replace("%", "")),
                volume=int(q["06. volume"]),
                latest_trading_day=q["07. latest trading day"],
            )
        except (ValueError, KeyError) as e:
            logger.error("Quote-Parsing-Fehler für %s: %s", symbol, e)
            return None

    # ──────────────────────────────────────────────────────────
    # Technische Indikatoren
    # ──────────────────────────────────────────────────────────

    def _latest_indicator_value(self, data: Dict, key: str) -> Optional[float]:
        """Gibt den neuesten Wert aus einem Indikatoren-Response zurück."""
        series = data.get(f"Technical Analysis: {key}", {})
        if not series:
            return None
        latest_date = max(series.keys())
        try:
            return float(series[latest_date][key])
        except (KeyError, ValueError):
            return None

    def get_rsi(self, symbol: str, interval: str = "daily", time_period: int = 14) -> Optional[float]:
        data = self._get({
            "function": "RSI",
            "symbol": symbol,
            "interval": interval,
            "time_period": time_period,
            "series_type": "close",
        })
        return self._latest_indicator_value(data, "RSI") if data else None

    def get_macd(self, symbol: str, interval: str = "daily") -> Dict[str, Optional[float]]:
        data = self._get({
            "function": "MACD",
            "symbol": symbol,
            "interval": interval,
            "series_type": "close",
        })
        result = {"macd": None, "signal": None, "hist": None}
        if not data:
            return result
        series = data.get("Technical Analysis: MACD", {})
        if not series:
            return result
        latest = series[max(series.keys())]
        try:
            result["macd"] = float(latest["MACD"])
            result["signal"] = float(latest["MACD_Signal"])
            result["hist"] = float(latest["MACD_Hist"])
        except (KeyError, ValueError) as e:
            logger.error("MACD-Parsing-Fehler: %s", e)
        return result

    def get_sma(self, symbol: str, period: int, interval: str = "daily") -> Optional[float]:
        data = self._get({
            "function": "SMA",
            "symbol": symbol,
            "interval": interval,
            "time_period": period,
            "series_type": "close",
        })
        return self._latest_indicator_value(data, "SMA") if data else None

    def get_technical_signals(self, symbol: str) -> TechnicalSignals:
        """Holt RSI, MACD und SMA-20/50 in einem Aufruf-Block."""
        logger.info("Hole technische Indikatoren für %s...", symbol)

        rsi = self.get_rsi(symbol)
        time.sleep(_REQUEST_DELAY)

        macd_data = self.get_macd(symbol)
        time.sleep(_REQUEST_DELAY)

        sma_20 = self.get_sma(symbol, 20)
        time.sleep(_REQUEST_DELAY)

        sma_50 = self.get_sma(symbol, 50)

        return TechnicalSignals(
            symbol=symbol,
            rsi=rsi,
            macd=macd_data["macd"],
            macd_signal=macd_data["signal"],
            macd_hist=macd_data["hist"],
            sma_20=sma_20,
            sma_50=sma_50,
        )

    # ──────────────────────────────────────────────────────────
    # News & Sentiment
    # ──────────────────────────────────────────────────────────

    def get_news_sentiment(self, symbol: str, limit: int = 5) -> List[NewsItem]:
        """News Sentiment für ein Symbol (letzte `limit` Artikel)."""
        data = self._get({
            "function": "NEWS_SENTIMENT",
            "tickers": symbol,
            "limit": min(limit * 3, 50),  # Mehr abrufen, dann filtern
            "sort": "LATEST",
        })
        if not data:
            return []

        items: List[NewsItem] = []
        for article in data.get("feed", []):
            # Nur Artikel nehmen, die den Ticker direkt erwähnen
            ticker_sentiments = article.get("ticker_sentiment", [])
            score = None
            for ts in ticker_sentiments:
                if ts.get("ticker", "").upper() == symbol.upper():
                    try:
                        score = float(ts["ticker_sentiment_score"])
                    except (KeyError, ValueError):
                        pass
                    break

            if score is None:
                continue

            label = article.get("overall_sentiment_label", "Neutral")
            items.append(NewsItem(
                title=article.get("title", ""),
                url=article.get("url", ""),
                source=article.get("source", ""),
                sentiment_score=score,
                sentiment_label=label,
            ))

            if len(items) >= limit:
                break

        return items

    def get_all_data(self, symbol: str):
        """
        Komplettes Datenpaket für ein Symbol.
        Gibt (Quote, TechnicalSignals, List[NewsItem]) zurück.
        """
        quote = self.get_quote(symbol)
        time.sleep(_REQUEST_DELAY)

        signals = self.get_technical_signals(symbol)
        time.sleep(_REQUEST_DELAY)

        news = self.get_news_sentiment(symbol)

        return quote, signals, news
