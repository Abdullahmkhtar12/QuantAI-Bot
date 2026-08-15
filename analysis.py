"""Technical analysis primitives for QuantAI.

The module intentionally uses transparent Pandas/Numpy calculations instead of
claiming that any indicator produces a guaranteed prediction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

try:  # Optional acceleration when TA-Lib is installed.
    import talib  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    talib = None


REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize an OHLCV frame and reject malformed input."""
    if frame is None or frame.empty:
        raise ValueError("No market data was returned")
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(column[0]) for column in data.columns]
    data.columns = [str(column).title() for column in data.columns]
    for column in REQUIRED_COLUMNS:
        if column not in data.columns:
            if column == "Volume" and "Volume" not in data.columns:
                data["Volume"] = 0.0
            else:
                raise ValueError(f"Missing OHLCV column: {column}")
    data = data[list(REQUIRED_COLUMNS)].apply(pd.to_numeric, errors="coerce").dropna()
    data = data[~data.index.duplicated(keep="last")].sort_index()
    if len(data) < 60:
        raise ValueError("At least 60 candles are required for analysis")
    return data


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.fillna(50.0)


def _atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = data["Close"].shift(1)
    true_range = pd.concat(
        [data["High"] - data["Low"], (data["High"] - previous_close).abs(), (data["Low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _macd(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd = _ema(series, 12) - _ema(series, 26)
    signal = _ema(macd, 9)
    return macd, signal, macd - signal


def _candlestick_label(data: pd.DataFrame) -> str:
    candle = data.iloc[-1]
    previous = data.iloc[-2]
    body = abs(candle.Close - candle.Open)
    candle_range = max(candle.High - candle.Low, 1e-12)
    upper_wick = candle.High - max(candle.Open, candle.Close)
    lower_wick = min(candle.Open, candle.Close) - candle.Low
    if body / candle_range < 0.12:
        return "Doji"
    if lower_wick > body * 2 and upper_wick < body:
        return "Bullish Hammer" if candle.Close >= candle.Open else "Potential Hammer"
    if upper_wick > body * 2 and lower_wick < body:
        return "Bearish Shooting Star" if candle.Close <= candle.Open else "Potential Shooting Star"
    prev_bearish = previous.Close < previous.Open
    prev_bullish = previous.Close > previous.Open
    current_bullish = candle.Close > candle.Open
    current_bearish = candle.Close < candle.Open
    if prev_bearish and current_bullish and candle.Open <= previous.Close and candle.Close >= previous.Open:
        return "Bullish Engulfing"
    if prev_bullish and current_bearish and candle.Open >= previous.Close and candle.Close <= previous.Open:
        return "Bearish Engulfing"
    return "Bullish Candle" if current_bullish else "Bearish Candle"


def calculate_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Add trend, momentum, volatility, and candlestick columns."""
    result = normalize_ohlcv(data)
    close = result["Close"]
    if talib is not None:
        result["EMA20"] = talib.EMA(close.values, timeperiod=20)
        result["EMA50"] = talib.EMA(close.values, timeperiod=50)
        result["RSI14"] = talib.RSI(close.values, timeperiod=14)
        result["ATR14"] = talib.ATR(result.High.values, result.Low.values, close.values, timeperiod=14)
        macd, macd_signal, macd_hist = talib.MACD(close.values, 12, 26, 9)
        result["MACD"] = macd
        result["MACDSignal"] = macd_signal
        result["MACDHistogram"] = macd_hist
    else:
        result["EMA20"] = _ema(close, 20)
        result["EMA50"] = _ema(close, 50)
        result["RSI14"] = _rsi(close)
        result["ATR14"] = _atr(result)
        result["MACD"], result["MACDSignal"], result["MACDHistogram"] = _macd(close)
    result["BBMiddle"] = close.rolling(20, min_periods=20).mean()
    deviation = close.rolling(20, min_periods=20).std(ddof=0)
    result["BBUpper"] = result["BBMiddle"] + (2 * deviation)
    result["BBLower"] = result["BBMiddle"] - (2 * deviation)
    result["VolumeSMA20"] = result["Volume"].rolling(20, min_periods=20).mean()
    result["Candle"] = [_candlestick_label(result.iloc[:i]) if i >= 2 else "" for i in range(len(result))]
    return result.dropna(subset=["EMA20", "EMA50", "RSI14", "ATR14", "MACDHistogram", "BBUpper", "BBLower"])


@dataclass(frozen=True)
class TechnicalSnapshot:
    symbol: str
    timeframe: str
    price: float
    ema20: float
    ema50: float
    rsi: float
    atr: float
    macd_histogram: float
    bb_upper: float
    bb_lower: float
    candle: str
    trend: str
    volatility: str


def snapshot(data: pd.DataFrame, symbol: str, timeframe: str) -> TechnicalSnapshot:
    indicators = calculate_indicators(data)
    row = indicators.iloc[-1]
    trend = "bullish" if row.EMA20 > row.EMA50 else "bearish"
    volatility = "high" if row.ATR14 / max(row.Close, 1e-12) > 0.012 else "normal"
    return TechnicalSnapshot(
        symbol=symbol.upper(), timeframe=timeframe, price=float(row.Close), ema20=float(row.EMA20),
        ema50=float(row.EMA50), rsi=float(row.RSI14), atr=float(row.ATR14),
        macd_histogram=float(row.MACDHistogram), bb_upper=float(row.BBUpper),
        bb_lower=float(row.BBLower), candle=str(row.Candle), trend=trend, volatility=volatility,
    )


def snapshot_dict(data: pd.DataFrame, symbol: str, timeframe: str) -> dict[str, Any]:
    return snapshot(data, symbol, timeframe).__dict__
