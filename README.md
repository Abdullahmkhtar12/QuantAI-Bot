# QuantAI Telegram Trading-Analysis Bot

> **تنبيه مالي:** هذا المشروع أداة تحليل تعليمية، وليس نصيحة مالية أو نظام تداول آلي. لا ينفّذ صفقات ولا يضمن دقة الإشارات. قيمة `0.985` هي عتبة ترشيح heuristic قابلة للضبط، وليست احتمال نجاح مثبتًا بإحصاء أو اختبار خلفي.

## ما الذي يقدمه المشروع؟

يستخدم QuantAI مكتبة `python-telegram-bot` الحديثة لمعالجة `/start` و`/analyze <symbol>` والأزرار التفاعلية. ويجلب بيانات OHLCV عبر `yfinance`، ثم يحسب EMA20 وEMA50 وRSI14 وMACD وATR وBollinger Bands ويقرأ نماذج شموع أساسية. بعد ذلك يولّد قرارًا `BUY` أو `SELL` أو `HOLD` وفق تصويت قابل للتفسير، ويُنشئ رسمًا بصيغة PNG يتضمن خطوط Entry وSL وTP عندما تتجاوز النتيجة العتبة.

تُحفظ الأسرار في `.env` ولا يجب إضافتها إلى Git. في التشغيل الحقيقي، يجب إلغاء رمز Telegram الذي ظهر في المحادثة وإصدار رمز جديد قبل استخدام الروبوت.

## هيكل المشروع

| المسار | الغرض |
|---|---|
| `bot.py` | نقطة تشغيل Telegram، الأوامر، الأزرار، وإرسال الرسوم |
| `quantai/data.py` | جلب وتطبيع بيانات OHLCV وتطبيع الرموز |
| `quantai/analysis.py` | المؤشرات الفنية ونماذج الشموع |
| `quantai/signals.py` | قواعد التصويت واحتساب العتبة والإشارة التعليمية |
| `quantai/chart.py` | إنشاء مخطط PNG عبر `mplfinance` أو `matplotlib` |
| `tests/` | اختبارات دون الاعتماد على الإنترنت باستخدام بيانات حتمية |
| `Dockerfile` و`docker-compose.yml` | تشغيل قابل لإعادة التشغيل |

## التشغيل المحلي

أنشئ بيئة افتراضية وثبّت الاعتمادات:

```bash
cd /home/ubuntu/quantai_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

قبل التشغيل، استبدل الرمز المكشوف برمز جديد من BotFather ثم حدّث `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=ضع_الرمز_الجديد_هنا
DEFAULT_TIMEFRAME=1h
DATA_PERIOD=6mo
SIGNAL_CONFIDENCE_THRESHOLD=0.985
CHART_DIR=charts
```

شغّل الاختبارات ثم البوت:

```bash
pytest -q
python bot.py
```

في Telegram أرسل `/start`، ثم `/analyze XAUUSD`. الرموز المدعومة لها اختصارات مريحة مثل `XAUUSD` و`BTCUSD` و`EURUSD`، ويمكن تمرير رموز Yahoo Finance أخرى.

## التشغيل عبر Docker

بعد إضافة رمز جديد صالح إلى `.env`:

```bash
docker compose up -d --build
docker compose logs -f quantai
```

لإيقاف الخدمة:

```bash
docker compose down
```

يستخدم Compose سياسة `unless-stopped`، ولذلك يعيد تشغيل الحاوية بعد الأعطال وإعادة تشغيل الخادم. لا تعتمد على مجلد العمل المؤقت لتشغيل 24/7؛ استخدم جهازًا محليًا يبقى متصلًا أو خدمة استضافة دائمة.

## التشغيل عبر systemd على خادم Linux

انسخ المشروع إلى خادم دائم، أنشئ البيئة الافتراضية وثبّت المتطلبات، ثم أنشئ الخدمة التالية مع تعديل المستخدم والمسار:

```ini
[Unit]
Description=QuantAI Telegram analysis bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/quantai_bot
EnvironmentFile=/opt/quantai_bot/.env
ExecStart=/opt/quantai_bot/.venv/bin/python /opt/quantai_bot/bot.py
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

احفظها باسم `/etc/systemd/system/quantai.service` ثم نفّذ:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now quantai
sudo systemctl status quantai
journalctl -u quantai -f
```

## الاختبارات والحدود

الاختبارات تستخدم بيانات اصطناعية حتمية فقط للتحقق من الحسابات وإنشاء الصورة. التشغيل الإنتاجي يستخدم بيانات السوق الخارجية، ولذلك قد يتأثر بتأخر المصدر أو انقطاعه أو اختلاف ساعات التداول. كما أن العتبة العالية قد تعيد `HOLD` كثيرًا، وهذا مقصود لتجنب عرض إشارات غير قوية وفق القواعد المحددة؛ لا ينبغي تفسيرها كدليل على دقة 98.5%.

## بدائل الاستضافة المستمرة

| الطريقة | المزايا | المقايضة | التعقيد |
|---|---|---|---|
| تشغيل محلي دائم | لا يتطلب خدمة مدفوعة إضافية ويتيح التحكم الكامل | يجب إبقاء الجهاز متصلًا | منخفض |
| Docker على خادم أو استضافة دائمة | إعادة تشغيل تلقائي وعزل نسبي وسهولة نقل | يحتاج خادمًا وإدارة أسرار | متوسط |
| WebDev باستضافة عملية دائمة | خدمة مُدارة مناسبة لعملية Telegram مستمرة ضمن موارد محدودة | تكلفة استخدامية بحسب الاستضافة ويحتاج تكييفًا مع بيئة المنصة | متوسط |

لروبوت Python يعتمد على مكتبات علمية وعميل Telegram، يكون Docker أو خادم Linux المعتاد أبسط مسار تشغيلي. أما التشغيل داخل هذه الجلسة المحلية فهو مناسب للاختبار فقط وليس ضمانًا لبقاء الخدمة بعد انتهاء الجلسة.

## مراجع تقنية

[1]: https://docs.python-telegram-bot.org/ "python-telegram-bot documentation"
[2]: https://pandas.pydata.org/docs/ "Pandas documentation"
[3]: https://github.com/matplotlib/mplfinance "mplfinance project"
[4]: https://github.com/ranaroussi/yfinance "yfinance project"
