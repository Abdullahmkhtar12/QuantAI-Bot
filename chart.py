"""PNG chart generation for Telegram responses."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from analysis import calculate_indicators
from signals import Signal

try:
    import mplfinance as mpf
except ImportError:  # pragma: no cover
    mpf = None


def create_chart(data: pd.DataFrame, signal: Signal, output_dir: str | Path = "charts") -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    indicators = calculate_indicators(data).tail(120)
    path = output / f"{signal.symbol}_{signal.timeframe.replace('/', '_')}.png"
    if mpf is not None:
        plot_data = indicators[["Open", "High", "Low", "Close", "Volume"]].copy()
        addplots = [
            mpf.make_addplot(indicators.EMA20, color="#4f9cff", width=1),
            mpf.make_addplot(indicators.EMA50, color="#ffb347", width=1),
        ]
        hlines = []
        colors = []
        if signal.entry is not None:
            hlines.append(signal.entry); colors.append("#2ecc71")
        if signal.stop_loss is not None:
            hlines.append(signal.stop_loss); colors.append("#e74c3c")
        if signal.take_profit is not None:
            hlines.append(signal.take_profit); colors.append("#9b59b6")
        mpf.plot(
            plot_data, type="candle", style="charles", volume=True, addplot=addplots,
            hlines=dict(hlines=hlines, colors=colors, linestyle="--", linewidths=(1.2,)),
            title=f"{signal.symbol} | {signal.timeframe} | {signal.action} | heuristic {signal.confidence:.1%}",
            ylabel="Price", savefig=dict(fname=str(path), dpi=160, bbox_inches="tight"),
        )
        return path

    fig, (ax, volume_ax) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [4, 1]})
    ax.plot(indicators.index, indicators.Close, label="Close", color="#1f77b4")
    ax.plot(indicators.index, indicators.EMA20, label="EMA20", color="#4f9cff")
    ax.plot(indicators.index, indicators.EMA50, label="EMA50", color="#ffb347")
    for value, label, color in ((signal.entry, "Entry", "#2ecc71"), (signal.stop_loss, "SL", "#e74c3c"), (signal.take_profit, "TP", "#9b59b6")):
        if value is not None:
            ax.axhline(value, linestyle="--", color=color, label=f"{label}: {value:.5f}")
    volume_ax.bar(indicators.index, indicators.Volume, color="#888888", width=0.02)
    ax.set_title(f"{signal.symbol} | {signal.timeframe} | {signal.action} | heuristic {signal.confidence:.1%}")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.25)
    volume_ax.set_ylabel("Volume")
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path
