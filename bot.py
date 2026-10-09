import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, OPERATORS
from opencellid import lookup_cell, CellLookupError

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# State sementara per chat — simpan hasil terakhir buat callback button
LAST_RESULT: dict[int, dict] = {}


# ─────────────────────────────────────────────
#  HANDLER: /start
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "📡 *BTS Tracker Bot*\n\n"
        "Kirim data BTS dengan format:\n"
        "`MCC MNC LAC CELL_ID`\n\n"
        "Contoh:\n"
        "`510 10 12345 67890`\n\n"
        "Cara dapat data: install *Signal Detector* atau *CellMapper* "
        "di Android target.\n\n"
        "Ketik /help buat info lengkap."
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


# ─────────────────────────────────────────────
#  HANDLER: /help
# ─────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Panduan*\n\n"
        "*Format input:*\n"
        "`MCC MNC LAC CELL_ID`\n\n"
        "*Kode operator Indonesia:*\n"
        "• 510 10 — Telkomsel\n"
        "• 510 11 — XL Axiata\n"
        "• 510 21 — Indosat\n"
        "• 510 08 — Tri\n"
        "• 510 09 — Smartfren\n\n"
        "*Command:*\n"
        "/start — menu utama\n"
        "/help — panduan ini\n"
        "/lookup — mode input interaktif\n"
        "/cancel — batalin input\n\n"
        "*Limit:* 1000 request/hari (free tier OpenCellID)."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ─────────────────────────────────────────────
#  HANDLER: /lookup — inline keyboard operator
# ─────────────────────────────────────────────
async def cmd_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Telkomsel (510 10)", callback_data="op:510:10"),
            InlineKeyboardButton("XL (510 11)", callback_data="op:510:11"),
        ],
        [
            InlineKeyboardButton("Indosat (510 21)", callback_data="op:510:21"),
            InlineKeyboardButton("Tri (510 08)", callback_data="op:510:08"),
        ],
        [
            InlineKeyboardButton("Smartfren (510 09)", callback_data="op:510:09"),
        ],
        [
            InlineKeyboardButton("🔙 Batal", callback_data="cancel"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Pilih operator target:",
        reply_markup=reply_markup,
    )


# ─────────────────────────────────────────────
#  HANDLER: teks bebas — parse "MCC MNC LAC CELL_ID"
# ─────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split()

    if len(parts) != 4:
        await update.message.reply_text(
            "❌ Format salah. Kirim: `MCC MNC LAC CELL_ID`\n"
            "Contoh: `510 10 12345 67890`",
            parse_mode="Markdown",
        )
        return

    mcc, mnc, lac, cell_id = parts
    await _do_lookup(update, context, mcc, mnc, lac, cell_id)


# ─────────────────────────────────────────────
#  CORE: lookup + kirim hasil
# ─────────────────────────────────────────────
async def _do_lookup(update, context, mcc, mnc, lac, cell_id):
    msg = await update.effective_message.reply_text("⏳ Mencari BTS...")

    try:
        result = lookup_cell(mcc, mnc, lac, cell_id)
    except CellLookupError as e:
        await msg.edit_text(f"❌ {e}")
        return

    chat_id = update.effective_chat.id
    LAST_RESULT[chat_id] = result

    lat = result["lat"]
    lon = result["lon"]
    rng = result["range"]
    op_name = OPERATORS.get(f"{mcc}{mnc}", f"Unknown ({mcc}{mnc})")

    # Inline keyboard dengan aksi
    keyboard = [
        [
            InlineKeyboardButton(
                "🗺 Google Maps",
                url=f"https://www.google.com/maps?q={lat},{lon}",
            ),
            InlineKeyboardButton(
                "📌 OpenStreetMap",
                url=f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}",
            ),
        ],
        [
            InlineKeyboardButton(
                "📍 Kirim Lokasi",
                callback_data="send_location",
            ),
            InlineKeyboardButton(
                "🔁 Lookup Ulang",
                callback_data="relookup",
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    result_text = (
        f"✅ *BTS Ditemukan*\n\n"
        f"*Operator:* {op_name}\n"
        f"*MCC/MNC:* `{mcc}/{mnc}`\n"
        f"*LAC:* `{lac}`\n"
        f"*Cell ID:* `{cell_id}`\n\n"
        f"*Latitude:* `{lat}`\n"
        f"*Longitude:* `{lon}`\n"
        f"*Akurasi:* ±{rng} m\n\n"
        f"[Lihat di peta](https://www.google.com/maps?q={lat},{lon})"
    )

    await msg.edit_text(
        result_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


# ─────────────────────────────────────────────
#  HANDLER: callback button
# ─────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # wajib — kasih feedback ke Telegram

    data = query.data
    chat_id = update.effective_chat.id

    # Operator dipilih dari /lookup
    if data.startswith("op:"):
        _, mcc, mnc = data.split(":")
        context.user_data["pending_mcc"] = mcc
        context.user_data["pending_mnc"] = mnc
        await query.edit_message_text(
            f"Operator dipilih: *{OPERATORS.get(mcc+mnc, mcc+' '+mnc)}*\n\n"
            f"Sekarang kirim `LAC CELL_ID`\n"
            f"Contoh: `12345 67890`",
            parse_mode="Markdown",
        )
        return

    # Kirim lokasi native Telegram
    if data == "send_location":
        result = LAST_RESULT.get(chat_id)
        if not result:
            await query.edit_message_text("❌ Data hilang. Lookup ulang.")
            return
        await context.bot.send_location(
            chat_id=chat_id,
            latitude=result["lat"],
            longitude=result["lon"],
        )
        return

    # Lookup ulang pakai data terakhir
    if data == "relookup":
        result = LAST_RESULT.get(chat_id)
        if not result:
            await query.edit_message_text("❌ Nggak ada data. Kirim format baru.")
            return
        await _do_lookup(
            update,
            context,
            result["mcc"],
            result["mnc"],
            result["lac"],
            result["cellid"],
        )
        return

    # Batal
    if data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Dibatalkan.")
        return


# ─────────────────────────────────────────────
#  HANDLER: teks setelah operator dipilih (LAC CELL_ID)
# ─────────────────────────────────────────────
async def handle_lac_cell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mcc = context.user_data.get("pending_mcc")
    mnc = context.user_data.get("pending_mnc")
    if not mcc or not mnc:
        return  # bukan dalam mode /lookup

    parts = update.message.text.strip().split()
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Format: `LAC CELL_ID`\nContoh: `12345 67890`",
            parse_mode="Markdown",
        )
        return

    lac, cell_id = parts
    context.user_data.clear()
    await _do_lookup(update, context, mcc, mnc, lac, cell_id)


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("lookup", cmd_lookup))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
