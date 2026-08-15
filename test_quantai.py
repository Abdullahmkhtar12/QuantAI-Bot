from pathlib import Path

from quantai.analysis import calculate_indicators
from quantai.chart import create_chart
from quantai.data import MarketDataConfig, fetch_ohlcv
from quantai.signals import SignalGenerator


def test_indicators_and_snapshot_data():
    data = fetch_ohlcv("XAUUSD", MarketDataConfig(allow_demo_data=True))
    indicators = calculate_indicators(data)
    assert len(indicators) > 0
    assert {"EMA20", "EMA50", "RSI14", "ATR14", "MACDHistogram", "Candle"}.issubset(indicators.columns)


def test_signal_threshold_is_honored():
    data = fetch_ohlcv("XAUUSD", MarketDataConfig(allow_demo_data=True))
    signal = SignalGenerator(threshold=0.985).generate(data, "XAUUSD", "1h")
    assert 0.5 <= signal.confidence <= 0.999
    assert signal.educational_only is True
    if signal.action in {"BUY", "SELL"}:
        assert signal.confidence >= 0.985
        assert signal.entry is not None and signal.stop_loss is not None and signal.take_profit is not None


def test_chart_is_created(tmp_path: Path):
    data = fetch_ohlcv("XAUUSD", MarketDataConfig(allow_demo_data=True))
    signal = SignalGenerator(threshold=0.985).generate(data, "XAUUSD", "1h")
    chart = create_chart(data, signal, tmp_path)
    assert chart.exists()
    assert chart.stat().st_size > 1000
