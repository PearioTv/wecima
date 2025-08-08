import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler

TOKEN = "8232742441:AAFv3DLDkgRpMnDBGME6OXAyGBgs163Tc0E"
BASE_URL = "https://weciema.video"

# مراحل المحادثة
SEARCH, RESULTS, SEASONS, EPISODES = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🔍 بحث"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👋 مرحبًا! اضغط على زر البحث للبدء.", reply_markup=reply_markup)

    return SEARCH

async def search_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 أرسل اسم الفيلم أو المسلسل للبحث:")
    return RESULTS

async def search_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    search_url = f"{BASE_URL}/?s={query.replace(' ', '+')}"
    r = requests.get(search_url)
    soup = BeautifulSoup(r.text, "html.parser")

    results = soup.select(".ml-item a")
    if not results:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.")
        return SEARCH

    keyboard = []
    for item in results:
        title = item.get("oldtitle", "بدون عنوان")
        url = item["href"]
        keyboard.append([InlineKeyboardButton(title, callback_data=f"item|{url}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📌 اختر العمل:", reply_markup=reply_markup)
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")

    if data[0] == "item":
        url = data[1]
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")

        # محاولة معرفة إذا كان مسلسل أو فيلم
        seasons = soup.select(".les-title")
        if seasons:
            # مسلسل → عرض المواسم
            keyboard = []
            for s in seasons:
                season_title = s.text.strip()
                season_link = s.find_next("a")["href"]
                keyboard.append([InlineKeyboardButton(season_title, callback_data=f"season|{season_link}")])
            await query.message.reply_text("📂 اختر الموسم:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # فيلم → رابط iframe
            iframe = soup.find("iframe")
            if iframe:
                iframe_src = iframe["src"]
                await query.message.reply_text(f"🎬 رابط المشاهدة:\n{iframe_src}")
            else:
                await query.message.reply_text("❌ لم أستطع العثور على رابط المشاهدة.")

    elif data[0] == "season":
        url = data[1]
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")

        episodes = soup.select(".les-content a")
        keyboard = []
        for ep in episodes:
            ep_title = ep.text.strip()
            ep_link = ep["href"]
            keyboard.append([InlineKeyboardButton(ep_title, callback_data=f"episode|{ep_link}")])

        await query.message.reply_text("📺 اختر الحلقة:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data[0] == "episode":
        url = data[1]
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        iframe = soup.find("iframe")
        if iframe:
            iframe_src = iframe["src"]
            await query.message.reply_text(f"🎬 رابط المشاهدة:\n{iframe_src}")
        else:
            await query.message.reply_text("❌ لم أستطع العثور على رابط المشاهدة.")

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SEARCH: [MessageHandler(filters.Regex("^🔍 بحث$"), search_request)],
            RESULTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_results)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
