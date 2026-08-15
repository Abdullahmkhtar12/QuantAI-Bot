"""Explainable, rule-based signal generation."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import pandas as pd

from analysis import calculate_indicators


@dataclass(frozen=True)
class Signal:
    symbol: str
    timeframe: str
    action: str
    confidence: float
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    reasons: tuple[str, ...]
    candle: str
    created_at: str
    educational_only: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


class SignalGenerator:
    """Generate signals from independent rule votes.

    ``threshold`` is intentionally 0.985 by default to satisfy the requested
    strict filter. It is a heuristic score, not a backtested probability.
    """

    def __init__(self, threshold: float = 0.985, atr_stop_multiple: float = 1.5, reward_multiple: float = 2.0):
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        self.threshold = threshold
        self.atr_stop_multiple = atr_stop_multiple
        self.reward_multiple = reward_multiple

    def generate(self, data: pd.DataFrame, symbol: str, timeframe: str) -> Signal:
        indicators = calculate_indicators(data)
        row = indicators.iloc[-1]
        close = float(row.Close)
        atr = max(float(row.ATR14), close * 0.0001)
        bullish_votes: list[str] = []
        bearish_votes: list[str] = []

        if row.EMA20 > row.EMA50:
            bullish_votes.append("EMA20 فوق EMA50")
        elif row.EMA20 < row.EMA50:
            bearish_votes.append("EMA20 تحت EMA50")
        if row.MACDHistogram > 0:
            bullish_votes.append("زخم MACD إيجابي")
        elif row.MACDHistogram < 0:
            bearish_votes.append("زخم MACD سلبي")
        if 50 <= row.RSI14 <= 70:
            bullish_votes.append("RSI يدعم استمرارًا صاعدًا دون تشبع شديد")
        elif 30 <= row.RSI14 < 50:
            bearish_votes.append("RSI يميل للضعف دون تشبع شديد")
        elif row.RSI14 < 30:
            bullish_votes.append("RSI في نطاق تشبع بيعي")
        elif row.RSI14 > 70:
            bearish_votes.append("RSI في نطاق تشبع شرائي")
        if row.Close > row.BBMiddle:
            bullish_votes.append("السعر فوق متوسط Bollinger")
        else:
            bearish_votes.append("السعر تحت متوسط Bollinger")
        candle = str(row.Candle)
        if "Bullish" in candle or "Hammer" in candle:
            bullish_votes.append(f"نموذج شمعة: {candle}")
        if "Bearish" in candle or "Shooting" in candle:
            bearish_votes.append(f"نموذج شمعة: {candle}")

        total = max(len(bullish_votes) + len(bearish_votes), 1)
        bull_ratio = len(bullish_votes) / total
        bear_ratio = len(bearish_votes) / total
        if bull_ratio > bear_ratio:
            action, side_ratio, reasons = "BUY", bull_ratio, tuple(bullish_votes)
        elif bear_ratio > bull_ratio:
            action, side_ratio, reasons = "SELL", bear_ratio, tuple(bearish_votes)
        else:
            action, side_ratio, reasons = "HOLD", 0.5, ("تعارض بين قواعد الاتجاه والزخم والشموع",)

        # Agreement score: 0.5 is neutral, 1.0 means every rule agrees.
        confidence = min(0.999, max(0.5, 0.5 + (side_ratio - 0.5)))
        if action == "BUY" and confidence >= self.threshold:
            entry = close
            stop = entry - self.atr_stop_multiple * atr
            target = entry + self.reward_multiple * (entry - stop)
        elif action == "SELL" and confidence >= self.threshold:
            entry = close
            stop = entry + self.atr_stop_multiple * atr
            target = entry - self.reward_multiple * (stop - entry)
        else:
            action, entry, stop, target = "HOLD", None, None, None

        risk_reward = self.reward_multiple if entry is not None else None
        return Signal(
            symbol=symbol.upper(), timeframe=timeframe, action=action, confidence=float(confidence),
            entry=entry, stop_loss=stop, take_profit=target, risk_reward=risk_reward,
            reasons=reasons, candle=candle,
            created_at=datetime.now(timezone.utc).isoformat(), educational_only=True,
        )
