"""Market-data access for QuantAI."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .analysis import normalize_ohlcv

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None


SYMBOL_ALIASES = {
    # Yahoo Finance commonly exposes spot-gold analysis through GC=F.
    "XAUUSD": "GC=F",
    "GOLD": "GC=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "SPX": "^GSPC",
    "US500": "^GSPC",
}


@dataclass(frozen=True)
class MarketDataConfig:
    period: str = "6mo"
    interval: str = "1h"
    allow_demo_data: bool = False


def provider_symbol(symbol: str) -> str:
    clean = symbol.strip().upper().replace("/", "")
    return SYMBOL_ALIASES.get(clean, clean)


def _demo_data(rows: int = 240) -> pd.DataFrame:
    """Deterministic test data only; never used unless explicitly enabled."""
    index = pd.date_range(end=pd.Timestamp.utcnow(), periods=rows, freq="h")
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0002, 0.006, rows)
    close = 1900 * np.exp(np.cumsum(returns))
    spread = np.abs(rng.normal(2.5, 0.6, rows))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(1000, 10000, rows)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=index)


def fetch_ohlcv(symbol: str, config: MarketDataConfig | None = None) -> pd.DataFrame:
    settings = config or MarketDataConfig()
    if yf is None:
        if settings.allow_demo_data:
            return _demo_data()
        raise RuntimeError("yfinance is not installed")
    ticker = provider_symbol(symbol)
    frame = yf.Ticker(ticker).history(period=settings.period, interval=settings.interval, auto_adjust=False)
    if frame.empty and settings.allow_demo_data:
        return _demo_data()
    return normalize_ohlcv(frame)
