import sqlite3
import datetime
import threading
from flask import Flask, render_template_string, request, redirect, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН! Paste You Token Here!"
PORT = 5000

verified_users = {}
memory_images = [] # Для сайта (храним ссылки или данные)

# ==========================================
# 1. БАЗА ДАННЫХ (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, user_message TEXT, bot_answer TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, fact_text TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def save_history(user_id, username, user_msg, bot_msg):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    time_now = str(datetime.datetime.now())
    cursor.execute('INSERT INTO history (user_id, username, user_message, bot_answer, timestamp) VALUES (?, ?, ?, ?, ?)', (user_id, username, user_msg, bot_msg, time_now))
    conn.commit()
    conn.close()

def save_fact(user_id, fact_text):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    time_now = str(datetime.datetime.now())
    cursor.execute('INSERT INTO facts (user_id, fact_text, timestamp) VALUES (?, ?, ?)', (user_id, fact_text, time_now))
    conn.commit()
    conn.close()

# ==========================================
# 2. ГЕНЕРАТОР ЭМОДЗИ-АРТА (Без ИИ, без картинок)
# ==========================================
def generate_emoji_art(prompt_text):
    prompt_lower = prompt_text.lower()
    
    # Базовый пейзаж (небо, земля)
    sky = "☀️☁️☁️☁️☀️☁️☁️"
    ground = "🌿🌿🌿🌱🌿🌿🌿"
    
    # Словарь тем для эмодзи-арта
    if "медвед" in prompt_lower or "медведь" in prompt_lower:
        art = f"""
{sky}
   🐻  🌲
  /   \
 🌿🌿🌿🌿🌿
{ground}
🌲🌲🌲🌲🌲
"""
        caption = "🐻 Я нарисовал медведя в лесу!"
        
    elif "кот" in prompt_lower or "кошк" in prompt_lower:
        art = f"""
{sky}
  🐱  🐈
 /  \ 
🌿🌿🌿🌿🌿
{ground}
🌲🌲🌲🌲🌲
"""
        caption = "🐱 Я нарисовал кота на улице!"
        
    elif "дом" in prompt_lower or "домик" in prompt_lower:
        art = f"""
{sky}
   🏠
  /  \
 🌿🌿🌿🌿
{ground}
🌳🌳🌳🌳🌳
"""
        caption = "🏠 Я нарисовал домик!"
        
    elif "машина" in prompt_lower or "автомобиль" in prompt_lower:
        art = f"""
{sky}
   🚗
  /   \
 🌿🌿🌿🌿
{ground}
"""
        caption = "🚗 Я нарисовал машину!"
        
    elif "солнце" in prompt_lower:
        art = f"""
☀️☀️☀️☀️☀️
☀️☀️☀️☀️☀️
☀️☀️☀️☀️☀️
{ground}
"""
        caption = "☀️ Я нарисовал солнце!"
        
    else:
        # Универсальный ответ, если тема не найдена
        art = f"""
🌈🎨✨
   {prompt_text}
✨🎨🌈
🎨🎨🎨🎨🎨
"""
        caption = f"🎨 Я попытался нарисовать: «{prompt_text}»!"

    return art, caption

# ==========================================
# 3. ВЕБ-САЙТ (Редактор для загрузки и удаления)
# ==========================================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Эмодзи-Арт Редактор</title></head>
<body style="font-family: Arial;">
    <h1>🎨 Эмодзи-Арт Редактор</h1>
    <a href="/">Обновить</a><br><br>
    
    <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <input type="submit" value="Загрузить арт">
    </form>
    <hr>
    
    <div style="display: flex; flex-wrap: wrap;">
        {% for img in images %}
        <div style="border: 1px solid #ccc; margin: 10px; padding: 10px; width: 200px;">
            <p><b>{{ img.name }}</b></p>
            <pre style="background: #f0f0f0; padding: 10px;">{{ img.data }}</pre>
            <a href="/delete/{{ img.id }}">🗑️ Удалить</a>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, images=memory_images)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    if file.filename != '':
        content = file.read().decode('utf-8')
        new_id = len(memory_images)
        memory_images.append({"id": new_id, "name": file.filename, "data": content})
    return redirect(url_for('index'))

@app.route('/delete/<int:img_id>')
def delete_image(img_id):
    global memory_images
    memory_images = [img for img in memory_images if img['id'] != img_id]
    return redirect(url_for('index'))

# ==========================================
# 4. TELEGRAM БОТ
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    text_lower = user_text.lower().strip()

    # Капча
    if "я не робот" in text_lower:
        keyboard = [[InlineKeyboardButton("✅ Подтвердить", callback_data='verify_captcha')]]
        await update.message.reply_text("🔒 Докажи, что ты не робот.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if user_id not in verified_users:
        keyboard = [[InlineKeyboardButton("✅ Подтвердить", callback_data='verify_captcha')]]
        await update.message.reply_text("⛔ Доступ запрещен!", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- КОМАНДА ЭМОДЗИ-АРТ ---
    if text_lower.startswith("нарисуй") or text_lower.startswith("нарисуй"):
        emoji_art, caption = generate_emoji_art(user_text)
        # Отправляем как код (pre) в Telegram, чтобы сохранить форматирование
        await update.message.reply_text(f"{caption}\n\n```\n{emoji_art}\n```", parse_mode='Markdown')
        return

    # --- КОМАНДА САЙТ ---
    if text_lower.startswith("сайт") or "редактор" in text_lower:
        bot_answer = f"🌐 Открой редактор изображений в браузере: http://localhost:{PORT}\nТам можно загружать и удалять эмодзи-арт."
    
    # --- ОСТАЛЬНЫЕ КОМАНДЫ ---
    elif text_lower.startswith("запомни"):
        fact = user_text[7:].strip()
        if fact:
            save_fact(user_id, fact)
            bot_answer = f"✅ Запомнил: {fact}"
        else:
            bot_answer = "Напиши, что запомнить."
    
    elif text_lower == "статистика":
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM history")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM facts")
        count_facts = cursor.fetchone()[0]
        conn.close()
        bot_answer = f"📊 Статистика:\nСообщений: {count}\nЗапоминаний: {count_facts}"
        
    else:
        bot_answer = (f"Ты написал: «{user_text}».\n"
                      f"Попробуй:\n• «Нарисуй медведя»\n• «Нарисуй кота»\n• «сайт» (для редактора)")

    save_history(user_id, username, user_text, bot_answer)
    await update.message.reply_text(bot_answer)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'verify_captcha':
        verified_users[query.from_user.id] = True
        await query.edit_message_text("✅ Капча пройдена!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    await update.message.reply_text(
        f"👋 Привет! Я рисую эмодзи-арт!\n"
        f"• «Нарисуй медведя» — получу эмодзи-рисунок.\n"
        f"• «Нарисуй кота» — нарисую кота.\n"
        f"• «сайт» — открою редактор в браузере."
    )

# ==========================================
# 5. ЗАПУСК (Бот + Сайт одновременно)
# ==========================================
if __name__ == '__main__':
    init_db()
    
    # Запускаем сайт в отдельном потоке
    threading.Thread(target=lambda: app.run(port=PORT, debug=False, use_reloader=False)).start()
    
    # Запускаем бота
    application = ApplicationBuilder().token("ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН! Paste You Token Here!").build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_click))
    
    print(f"✅ Бот с эмодзи-артом запущен! Сайт: http://localhost:{PORT}")
    application.run_polling()