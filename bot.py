"""QuantAI Telegram bot entrypoint.

This bot provides educational market analysis only. It never places trades.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from quantai.chart import create_chart
from quantai.data import MarketDataConfig, fetch_ohlcv
from quantai.signals import Signal, SignalGenerator

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
LOGGER = logging.getLogger("quantai")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHART_DIR = Path(os.getenv("CHART_DIR", "charts"))
TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "1h")
DATA_PERIOD = os.getenv("DATA_PERIOD", "6mo")
SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_CONFIDENCE_THRESHOLD", "0.985"))

DISCLAIMER = (
    "\n\nتنبيه: QuantAI أداة تحليل تعليمية وليست نصيحة مالية أو ضمانًا للربح. "
    "لا ينفّذ الروبوت صفقات، ودرجة الثقة رقم ترشيح heuristic وليست احتمال نجاح مثبتًا."
)


def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Live Analysis", callback_data="live_analysis")],
        [InlineKeyboardButton("🚀 Active Signals", callback_data="active_signals")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
    ])


def format_signal(signal: Signal) -> str:
    confidence = f"{signal.confidence:.2%}"
    lines = [
        f"*{signal.symbol}* — `{signal.timeframe}`",
        f"القرار: *{signal.action}*",
        f"الترشيح الحسابي: `{confidence}` (العتبة: `{SIGNAL_THRESHOLD:.2%}`)",
    ]
    if signal.entry is not None:
        lines.extend([
            f"Entry: `{signal.entry:.5f}`",
            f"SL: `{signal.stop_loss:.5f}`",
            f"TP: `{signal.take_profit:.5f}`",
            f"Risk/Reward: `{signal.risk_reward:.2f}`",
        ])
    else:
        lines.append("لا توجد إشارة قابلة للتنفيذ وفق العتبة الصارمة؛ الحالة الحالية HOLD.")
    if signal.reasons:
        lines.append("الأسباب: " + "؛ ".join(signal.reasons[:5]))
    lines.append(f"نموذج الشمعة: `{signal.candle}`")
    return "\n".join(lines) + DISCLAIMER


async def _analyze_symbol(symbol: str, timeframe: str, context: ContextTypes.DEFAULT_TYPE) -> tuple[Signal, Path]:
    config = MarketDataConfig(period=DATA_PERIOD, interval=timeframe, allow_demo_data=False)
    data = await asyncio.to_thread(fetch_ohlcv, symbol, config)
    generator = SignalGenerator(threshold=SIGNAL_THRESHOLD)
    signal = generator.generate(data, symbol, timeframe)
    chart = await asyncio.to_thread(create_chart, data, signal, CHART_DIR)
    context.application.bot_data.setdefault("last_signals", {})[signal.symbol] = signal
    return signal, chart


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    await update.effective_message.reply_text(
        "مرحبًا بك في *QuantAI*، روبوت التحليل الفني التعليمي.\n\n"
        "استخدم `/analyze XAUUSD` لتحليل رمز، أو اختر من القائمة:",
        reply_markup=menu_keyboard(), parse_mode="Markdown",
    )


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    if not context.args:
        await update.effective_message.reply_text("الصيغة: `/analyze XAUUSD`", parse_mode="Markdown")
        return
    symbol = context.args[0].upper()
    timeframe = context.user_data.get("timeframe", TIMEFRAME)
    await update.effective_message.chat.send_action(ChatAction.UPLOAD_PHOTO)
    try:
        signal, chart = await _analyze_symbol(symbol, timeframe, context)
        await update.effective_message.reply_photo(photo=InputFile(chart.open("rb")), caption=format_signal(signal), parse_mode="Markdown")
    except Exception as exc:
        LOGGER.exception("Analysis failed for %s", symbol)
        await update.effective_message.reply_text(
            f"تعذر تحليل `{symbol}` حاليًا: `{type(exc).__name__}`. تحقق من الرمز أو مصدر البيانات.", parse_mode="Markdown"
        )


async def live_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_text("أرسل أمرًا مثل `/analyze XAUUSD` للحصول على تحليل حي.", reply_markup=menu_keyboard(), parse_mode="Markdown")


async def active_signals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    last_signals: dict[str, Signal] = context.application.bot_data.get("last_signals", {})
    actionable = [signal for signal in last_signals.values() if signal.action in {"BUY", "SELL"}]
    if actionable:
        text = "\n\n".join(format_signal(signal) for signal in actionable)
    else:
        text = "لا توجد إشارات نشطة محفوظة حاليًا. نفّذ `/analyze XAUUSD` أو رمزًا آخر أولًا."
    await query.edit_message_text(text, reply_markup=menu_keyboard(), parse_mode="Markdown")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    current = context.user_data.get("timeframe", TIMEFRAME)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Timeframe الحالي: {current}", callback_data="noop")],
        [InlineKeyboardButton("15m", callback_data="tf_15m"), InlineKeyboardButton("1h", callback_data="tf_1h"), InlineKeyboardButton("1d", callback_data="tf_1d")],
        [InlineKeyboardButton("عودة", callback_data="home")],
    ])
    await query.edit_message_text("إعدادات التحليل — اختر الإطار الزمني:", reply_markup=keyboard)


async def set_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer("تم تحديث الإطار الزمني")
    context.user_data["timeframe"] = query.data.removeprefix("tf_")
    await settings(update, context)


async def noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_text("القائمة الرئيسية:", reply_markup=menu_keyboard())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.exception("Unhandled Telegram error", exc_info=context.error)


def build_application() -> Application:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Add it to .env")
    bot_request = HTTPXRequest(connect_timeout=30, read_timeout=60, write_timeout=30, pool_timeout=30)
    updates_request = HTTPXRequest(connect_timeout=30, read_timeout=90, write_timeout=30, pool_timeout=30)
    app = (Application.builder().token(TOKEN).request(bot_request).get_updates_request(updates_request).build())
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CallbackQueryHandler(live_analysis, pattern="^live_analysis$"))
    app.add_handler(CallbackQueryHandler(active_signals, pattern="^active_signals$"))
    app.add_handler(CallbackQueryHandler(settings, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(set_timeframe, pattern="^tf_(15m|1h|1d)$"))
    app.add_handler(CallbackQueryHandler(home, pattern="^home$"))
    app.add_handler(CallbackQueryHandler(noop, pattern="^noop$"))
    app.add_error_handler(error_handler)
    return app


if __name__ == "__main__":
    LOGGER.info("Starting QuantAI polling bot")
    build_application().run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
