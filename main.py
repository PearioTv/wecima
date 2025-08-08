import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler

# ---------- إعدادات ----------
TOKEN = "ضع_توكن_البوت_هنا"
BASE_URL = "https://weciema.video"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8"
}

# مراحل المحادثة
SEARCH, RESULTS = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🔍 بحث"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👋 مرحبًا! اضغط زر 🔍 ثم اكتب اسم الفيلم أو المسلسل.", reply_markup=reply_markup)
    return SEARCH


def _safe_get(url, headers=HEADERS, use_cloudscraper=False, timeout=12):
    """
    محاولة جلب الصفحة أولاً بـ requests مع رؤوس المتصفح،
    وإن لم تنجح (مثل حماية Cloudflare)، يمكن تفعيل cloudscraper عن طريق use_cloudscraper=True.
    """
    try:
        if use_cloudscraper:
            import cloudscraper
            sc = cloudscraper.create_scraper()
            r = sc.get(url, headers=headers, timeout=timeout)
        else:
            r = requests.get(url, headers=headers, timeout=timeout)
        return r
    except Exception as e:
        # ارجع None عند الفشل
        return None


def extract_iframe_from_html(html, base=BASE_URL):
    """محاولة استخراج قيمة iframe أو data-src أو src ضمن سكربت"""
    soup = BeautifulSoup(html, "html.parser")
    # مباشرة iframe
    iframe = soup.find("iframe")
    if iframe and iframe.get("src"):
        return urljoin(base, iframe["src"])

    # بحث بالـ regex داخل الـ HTML
    m = re.search(r'iframe[^>]+src=["\']([^"\']+)["\']', html)
    if m:
        return urljoin(base, m.group(1))

    m2 = re.search(r'data-src=["\']([^"\']+)["\']', html)
    if m2:
        return urljoin(base, m2.group(1))

    # بعض مواقع المشاهدة تضع embed داخل سكربت
    m3 = re.search(r'src:\s*["\']([^"\']+)["\']', html)
    if m3:
        return urljoin(base, m3.group(1))

    return None


async def search_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 أرسل اسم الفيلم أو المسلسل للبحث:")
    return RESULTS


async def search_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    await update.message.reply_text(f"🔎 أبحث عن: {query} ...")

    # أول محاولة: استخدام صفحة البحث التقليدية
    search_url = f"{BASE_URL}/?s={query.replace(' ', '+')}"
    r = _safe_get(search_url)
    # إذا الصفحة فاضية أو قصيرة جداً، نجرب استخدام cloudscraper
    if not r or r.status_code != 200 or len(r.text) < 800:
        r = _safe_get(search_url, use_cloudscraper=True)

    if not r or r.status_code != 200:
        # fallback: حاول البحث داخل صفحات رئيسية/فئات (home, series, movies)
        candidates = []
        scan_pages = [f"{BASE_URL}/home/", f"{BASE_URL}/series/", f"{BASE_URL}/movies/"]
        for p in scan_pages:
            rp = _safe_get(p)
            if not rp or rp.status_code != 200:
                rp = _safe_get(p, use_cloudscraper=True)
            if not rp:
                continue
            soup_p = BeautifulSoup(rp.text, "html.parser")
            for a in soup_p.find_all("a", href=True):
                txt = a.get_text(strip=True)
                if txt and query.lower() in txt.lower():
                    href = urljoin(BASE_URL, a['href'])
                    candidates.append((txt, href))
        if not candidates:
            await update.message.reply_text("❌ لم يتم العثور على نتائج. جرّب كلمة مختلفة أو تأكد من اتصال الـ VPS/Replit بالإنترنت.")
            return SEARCH

        # عرض النتائج من الـ fallback
        keyboard = []
        seen = set()
        for title, href in candidates[:40]:
            if href in seen: continue
            seen.add(href)
            keyboard.append([InlineKeyboardButton(title, callback_data=f"item|{href}")])
        await update.message.reply_text("📌 اختر العمل:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    # الآن parsing صفحة البحث الفعلية
    soup = BeautifulSoup(r.text, "html.parser")

    # حاول selectors الشائعة أولاً
    results = soup.select(".ml-item a") or soup.select(".list-film a") or soup.select("article a")
    # لو لم نجد، ابحث عن أي <a> يحتوي نص البحث
    if not results:
        results = []
        for a in soup.find_all("a", href=True):
            txt = a.get_text(strip=True)
            if txt and query.lower() in txt.lower():
                results.append(a)

    if not results:
        await update.message.reply_text("❌ لم يتم العثور على نتائج (لم أجد عناصر مطابقة).")
        return SEARCH

    keyboard = []
    seen = set()
    for item in results:
        title = item.get("oldtitle") or item.get_text(strip=True) or "بدون عنوان"
        url = urljoin(BASE_URL, item["href"])
        if url in seen: continue
        seen.add(url)
        keyboard.append([InlineKeyboardButton(title, callback_data=f"item|{url}")])

    if not keyboard:
        await update.message.reply_text("❌ لم يتم العثور على نتائج قابلة للعرض.")
        return SEARCH

    await update.message.reply_text("📌 اختر العمل:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|", 1)
    typ = data[0]
    url = data[1]

    # جلب الصفحة (مع fallback للـ cloudscraper)
    r = _safe_get(url)
    if not r or r.status_code != 200 or len(r.text) < 400:
        r = _safe_get(url, use_cloudscraper=True)
    if not r:
        await query.message.reply_text("خطأ عند جلب الصفحة. حاول مرة أخرى لاحقًا.")
        return

    soup = BeautifulSoup(r.text, "html.parser")

    # إذا الصفحة تحتوي على حلقات (episodes) -> اجلب الروابط التي تحوي كلمة 'حلقة' أو روابط داخل قسم الحلقات
    ep_links = []
    # ابحث أولا عن روابط تحتوي كلمة حلقة بالـ text
    for a in soup.find_all("a", href=True):
        txt = a.get_text(strip=True)
        if txt and ("حلقة" in txt or "episode" in txt.lower() or "ep" in txt.lower()):
            href = urljoin(BASE_URL, a['href'])
            ep_links.append((txt, href))

    # إن وُجدت حلقات كثيرة، اعرضها مباشرة
    if ep_links:
        keyboard = []
        seen = set()
        for title, href in ep_links[:60]:
            if href in seen: continue
            seen.add(href)
            keyboard.append([InlineKeyboardButton(title, callback_data=f"episode|{href}")])
        await query.message.reply_text("📺 اختر الحلقة:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # خلاف ذلك: افترض أنه فيلم أو صفحة مشاهدة، حاول استخراج iframe
    iframe_src = extract_iframe_from_html(r.text, base=BASE_URL)
    if iframe_src:
        await query.message.reply_text(f"🎬 رابط المشاهدة (iframe):\n{iframe_src}")
        return

    # لو لم نجد شيء: حاول البحث عن روابط داخل مقطع خاص مثل 'server' أو 'watch'
    alt = None
    for a in soup.find_all("a", href=True):
        if any(k in a['href'] for k in ["/watch", "/player", "/embed", "/iframe"]):
            alt = urljoin(BASE_URL, a['href'])
            break
    if alt:
        await query.message.reply_text(f"قد يكون رابط المشاهدة هنا:\n{alt}")
        return

    await query.message.reply_text("❌ لم أجد رابط iframe أو حلقات في هذه الصفحة.")


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
