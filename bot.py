    """QuantAI Telegram bot entrypoint.

This bot provides educational market analysis only.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from chart import create_chart
from data import MarketDataConfig, fetch_ohlcv
from signals import Signal, SignalGenerator

# تحميل متغيرات البيئة من ملف .env إن وجد
load_dotenv()

# إعداد السجلات (Logging)
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)
LOGGER = logging.getLogger("quantai")

# قراءة المتغيرات الأساسية
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHART_DIR = Path(os.getenv("CHART_DIR", "charts"))
TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "1h")
DATA_PERIOD = os.getenv("DATA_PERIOD", "6mo")
SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_CONFIDENCE_THRESHOLD", "0.6"))

# تهيئة مكتبة Gemini بالمفتاح
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

DISCLAIMER = (
    "\n\nتنبيه: QuantAI أداة تحليل تعليمية وليست نصيحة مالية أو ضماناً للربح."
)


def get_main_keyboard() -> InlineKeyboardMarkup:
    """إنشاء لوحة الأزرار الرئيسية."""
    keyboard = [
        [
            InlineKeyboardButton("📊 تحليل عملة", callback_query_data="analyze_prompt"),
            InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("ℹ️ المساعدة", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أمر /start."""
    welcome_text = (
        "مرحباً بك في QuantAI! 🤖📈\n\n"
        "أنا بوت مساعد للتحليل الفني للأسواق المالية.\n"
        "يمكنك إرسال رمز العملة (مثل BTCUSDT) أو إرسال صورة رسم بياني لتحليلها بواسطة الذكاء الاصطناعي."
    )
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أمر /help."""
    help_text = (
        "💡 **كيفية استخدام البوت:**\n\n"
        "1. **تحليل نصي:** أرسل رمز الزوج مباشرة (مثال: `ETHUSDT` أو `BTCUSDT`).\n"
        "2. **تحليل صورة:** قم بإرسال صورة رسم بياني (Chart) وسأقوم بتحليل الشموع والنماذج لك.\n"
        "3. **الأوامر:** استخدم /start للوصول للقائمة الرئيسية."
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode="Markdown")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض إعدادات الإطار الزمني."""
    query = update.callback_query
    if query:
        await query.answer()

    tf = context.user_data.get("timeframe", TIMEFRAME) if context.user_data else TIMEFRAME

    keyboard = [
        [
            InlineKeyboardButton("15m", callback_data="tf_15m"),
            InlineKeyboardButton("1h", callback_data="tf_1h"),
            InlineKeyboardButton("4h", callback_data="tf_4h"),
            InlineKeyboardButton("1d", callback_data="tf_1d"),
        ],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="home")],
    ]

    msg = f"⚙️ **الإعدادات الحالية:**\nالفريم الزمني: `{tf}`"
    if query and query.message:
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def set_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تغيير الفريم الزمني للتحليل النصي."""
    query = update.callback_query
    if query and query.data:
        await query.answer()
        tf_selected = query.data.replace("tf_", "")
        if context.user_data is not None:
            context.user_data["timeframe"] = tf_selected
        await settings(update, context)


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """العودة للواجهة الرئيسية."""
    query = update.callback_query
    if query and query.message:
        await query.answer()
        await query.message.edit_text("🏠 القائمة الرئيسية:", reply_markup=get_main_keyboard())


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أسماء العملات المكتوبة نصياً."""
    if not update.message or not update.message.text:
        return

    symbol = update.message.text.strip().upper()
    status_msg = await update.message.reply_text(f"🔍 جاري تحليل الرمز {symbol}...")

    tf = context.user_data.get("timeframe", TIMEFRAME) if context.user_data else TIMEFRAME

    try:
        config = MarketDataConfig(symbol=symbol, timeframe=tf, period=DATA_PERIOD)
        df = await fetch_ohlcv(config)

        if df.empty:
            await status_msg.edit_text(f"❌ تعذر جلب البيانات للرمز `{symbol}`. تأكد من صحة الرمز.", parse_mode="Markdown")
            return

        generator = SignalGenerator(confidence_threshold=SIGNAL_THRESHOLD)
        signal: Signal = generator.generate(df, symbol=symbol)

        chart_path = CHART_DIR / f"{symbol}_{tf}.png"
        await create_chart(df, symbol=symbol, timeframe=tf, output_path=chart_path)

        report = (
            f"📊 **تقرير التحليل الفني: {symbol}**\n"
            f"⏱️ الفريم: `{tf}`\n"
            f"🎯 الاتجاه: **{signal.direction}**\n"
            f"💪 قوة الإشارة: `{signal.confidence:.2%}`\n\n"
            f"📝 **الملاحظات:**\n{signal.reasoning}"
            f"{DISCLAIMER}"
        )

        with open(chart_path, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=report, parse_mode="Markdown")

        await status_msg.delete()

    except Exception as e:
        LOGGER.exception("Error analyzing text symbol: %s", e)
        await status_msg.edit_text(f"❌ حدث خطأ أثناء تحليل الرمز `{symbol}`.")


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة الصور بواسطة نموذج Gemini."""
    if not update.message or not update.message.photo:
        return

    status_msg = await update.message.reply_text("📸 تم استلام صورة الرسم البياني! جاري معالجة الشموع اليابانية...")

    try:
        # تحميل أحدث وأعلى دقة للصورة
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        # تحويل البايتات إلى صورة باستخدام PIL
        image = Image.open(io.BytesIO(image_bytes))

        # تجهيز نموذج الذكاء الاصطناعي
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = (
            "أنت خبير تحليل فني في الأسواق المالية. قم بتحليل صورة الرسم البياني المرفقة للعملة الرقمية أو السهم.\n"
            "قدم التوصية بالتنسيق التالي:\n"
            "1. الاتجاه العام (صاعد / هابط / عرضي) 📈📉\n"
            "2. نقطة الدخول المقترحة (Entry Point) 🎯\n"
            "3. أهداف أخذ الربح (Take Profit) 💰\n"
            "4. وقف الخسارة (Stop Loss) 🛑\n"
            "5. ملخص سريع للتحليل الفني والنماذج السعرية المتوقعة."
        )

        # استدعاء Gemini بطريقة Async
        response = await asyncio.to_thread(model.generate_content, [prompt, image])

        if response and response.text:
            await status_msg.edit_text(response.text + DISCLAIMER)
        else:
            await status_msg.edit_text("⚠️ لم يتمكن النموذج من استخراج رد مناسب من الصورة.")

    except Exception as e:
        LOGGER.exception("Error in photo analysis: %s", e)
        await status_msg.edit_text("❌ حدث خطأ أثناء تحليل الصورة. تأكد من إعداد GEMINI_API_KEY بشكل صحيح.")


def main() -> None:
    """تشغيل تطبيق البوت."""
    if not TOKEN:
        LOGGER.error("TELEGRAM_BOT_TOKEN is missing!")
        return

    CHART_DIR.mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(TOKEN).build()

    # تسجيل الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # تسجيل الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(home, pattern="^home$"))
    app.add_handler(CallbackQueryHandler(settings, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(set_timeframe, pattern="^tf_"))

    # تسجيل معالجة الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    LOGGER.info("Starting QuantAI bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
