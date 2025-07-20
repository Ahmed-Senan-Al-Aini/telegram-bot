import os
import asyncio
import threading
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN")  # استبدل بالتوكن الخاص بك

user_cancel_flags = {}  # لتخزين علامات إلغاء التحميل لكل مستخدم

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 أرسل رابط الفيديو وسأقوم بتحميله بالجودة الافتراضية.")

def create_progress_bar(percent_str):
    try:
        percent_num = float(percent_str.replace('%', '').strip())
    except:
        percent_num = 0
    blocks = int(percent_num // 10)
    bar = '█' * blocks + '░' * (10 - blocks)
    return f"[{bar}]"

def get_progress_hook(message, loop, cancel_flag):
    def hook(d):
        if cancel_flag.is_set():
            raise Exception("تم إلغاء التحميل من قبل المستخدم")

        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '').strip()
            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            bar = create_progress_bar(percent)
            text = f"📥 جاري التحميل...\n{bar} {percent}\n⚡ السرعة: {speed}\n⏳ الوقت المتبقي: {eta}"

            asyncio.run_coroutine_threadsafe(message.edit_text(text), loop)

        elif d['status'] == 'finished':
            asyncio.run_coroutine_threadsafe(message.edit_text("✅ تم تحميل الملف، جاري الإرسال..."), loop)

    return hook

async def send_file(context, chat_id, file_path):
    try:
        with open(file_path, 'rb') as f:
            await context.bot.send_video(chat_id=chat_id, video=f)
    except Exception as e:
        print(f"Error sending file: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ حدث خطأ أثناء إرسال الملف.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    flag = user_cancel_flags.get(user_id)
    if flag:
        flag.set()
        await query.edit_message_text("❌ تم إلغاء تحميل الفيديو حسب طلبك.")
    else:
        await query.answer("لا يوجد تحميل جاري للإلغاء.", show_alert=True)

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    cancel_flag = threading.Event()
    user_cancel_flags[user_id] = cancel_flag

    cancel_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ إلغاء التحميل", callback_data='cancel')
    ]])

    msg = await update.message.reply_text("🔄 جاري بدء التحميل...", reply_markup=cancel_keyboard)
    loop = asyncio.get_event_loop()

    def thread_download():
        try:
            ydl_opts = {
                'outtmpl': '%(title)s.%(ext)s',
                # لا نحدد 'format' لتحميل الجودة الافتراضية
                'progress_hooks': [get_progress_hook(msg, loop, cancel_flag)],
                'quiet': True,
                'noplaylist': True,
                'merge_output_format': 'mp4',
                'postprocessors': [{'key': 'FFmpegMerger'}],
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)

            user_cancel_flags.pop(user_id, None)

            asyncio.run_coroutine_threadsafe(send_file(context, update.message.chat.id, file_path), loop)

        except Exception as e:
            user_cancel_flags.pop(user_id, None)
            if str(e) == "تم إلغاء التحميل من قبل المستخدم":
                asyncio.run_coroutine_threadsafe(msg.edit_text("❌ تم إلغاء تحميل الفيديو حسب طلبك."), loop)
            else:
                print(f"Error during download: {e}")
                asyncio.run_coroutine_threadsafe(msg.edit_text("❌ فشل التحميل. تأكد من صحة الرابط."), loop)

    threading.Thread(target=thread_download).start()

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    app.add_handler(CallbackQueryHandler(cancel_handler, pattern='^cancel$'))

    PORT = int(os.environ.get("PORT", 8443))

    print("🚀 Bot running with Webhook on Render...")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://telegram-bot-0ap0.onrender.com/{TOKEN}"
    )
