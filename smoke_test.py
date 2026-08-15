from pathlib import Path

from quantai.chart import create_chart
from quantai.data import MarketDataConfig, fetch_ohlcv
from quantai.signals import SignalGenerator


def main() -> None:
    data = fetch_ohlcv("XAUUSD", MarketDataConfig(period="1mo", interval="1h"))
    signal = SignalGenerator(threshold=0.985).generate(data, "XAUUSD", "1h")
    chart = create_chart(data, signal, Path("charts"))
    print({"rows": len(data), "action": signal.action, "confidence": round(signal.confidence, 4), "chart": str(chart)})


if __name__ == "__main__":
    main()
