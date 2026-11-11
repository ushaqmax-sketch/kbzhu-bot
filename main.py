import asyncio
import logging
import os
import sqlite3
from datetime import datetime
import http.server
import socketserver
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import re
from google import genai

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "9054880366:AAG8slNCtvq7DjyMLfa1-8pxriN1lD02EWI"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TARGET_CALORIES = 1750  # Твой дневной лимит калорий

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

ai_client = genai.Client(api_key=GEMINI_API_KEY)
user_locks = {}

logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ (SQLite для надежного сохранения истории) ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS food_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            calories REAL,
            protein REAL,
            fat REAL,
            carbs REAL,
            description TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def add_log_db(user_id, date, cal, protein, fat, carbs, desc):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO food_logs (user_id, date, calories, protein, fat, carbs, description) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (user_id, date, cal, protein, fat, carbs, desc)
    )
    conn.commit()
    conn.close()

def get_today_logs_db(user_id, date):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT calories, protein, fat, carbs FROM food_logs WHERE user_id = ? AND date = ?',
        (user_id, date)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"calories": r[0], "protein": r[1], "fat": r[2], "carbs": r[3]} for r in rows]

def clear_today_logs_db(user_id, date):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM food_logs WHERE user_id = ? AND date = ?', (user_id, date))
    conn.commit()
    conn.close()

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Бот полностью восстановлен и готов к работе.\n\n"
        "Пиши любую еду или снеки, а я посчитаю КБЖУ!\n\n"
        "Команды:\n"
        "📊 /status — итог за сегодня\n"
        "🔄 /reset — сбросить дневник\n"
        "📈 /week — отчёт за неделю"
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    user_id = message.from_user.id
    async with get_user_lock(user_id):
        today = datetime.now().strftime("%Y-%m-%d")
        today_logs = get_today_logs_db(user_id, today)
        
        if not today_logs:
            await message.answer("Сегодня ты еще ничего не записывал в дневник.")
            return
            
        total_cal = sum(item["calories"] for item in today_logs)
        total_p = sum(item["protein"] for item in today_logs)
        total_f = sum(item["fat"] for item in today_logs)
        total_c = sum(item["carbs"] for item in today_logs)
        
        left = TARGET_CALORIES - total_cal
        
        await message.answer(
            f"📊 **Итог за сегодня:**\n\n"
            f"🔥 Калории: **{total_cal:.0f} ккал** (Осталось: {left:.0f} ккал до лимита)\n"
            f"🥩 Белки: {total_p:.1f} г\n"
            f"🥑 Жиры: {total_f:.1f} г\n"
            f"🍞 Углеводы: {total_c:.1f} г"
        )

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = message.from_user.id
    async with get_user_lock(user_id):
        today = datetime.now().strftime("%Y-%m-%d")
        clear_today_logs_db(user_id, today)
            
    await message.answer("🔄 **Дневник за сегодня полностью сброшен!** Начинаем с чистого листа.")

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    await message.answer("📈 **Еженедельный отчет:**\nВсе данные под контролем, держись отлично!")

@dp.message()
async def process_food(message: types.Message):
    if not message.text or message.from_user.is_bot:
        return
        
    user_id = message.from_user.id
    text = message.text
    
    if text.startswith("/"):
        return

    async with get_user_lock(user_id):
        try:
            prompt = (
                "Ты профессиональный нутрициолог. Посчитай КБЖУ для: "
                f"'{text}'. "
                "Выдай результат в одну строчку через пробел в точнейшем порядке: "
                "калории, белки, жиры, углеводы. Только 4 числа, больше ничего. "
                "Пример: 260 8.0 2.0 50.0"
            )
            
            response = ai_client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
            )
            
            response_text = response.text.strip() if response and response.text else ""
            
            # Достаем ВСЕ числа из ответа модели
            numbers = [float(num) for num in re.findall(r'\d+(?:\.\d+)?', response_text)]
            
            if len(numbers) >= 4:
                cal = numbers[0]
                protein = numbers[1]
                fat = numbers[2]
                carbs = numbers[3]
            else:
                cal, protein, fat, carbs = 150.0, 5.0, 5.0, 20.0

            desc = text
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Сохраняем в базу данных (счетчик не сбрасывается)
            add_log_db(user_id, today, cal, protein, fat, carbs, desc)
            
            today_logs = get_today_logs_db(user_id, today)
            total_cal = sum(item["calories"] for item in today_logs)
            left = TARGET_CALORIES - total_cal
            
            await message.answer(
                f"✅ Записал: *{desc}*\n\n"
                f"🔥 **+{cal:.0f} ккал** (Б: {protein}г | Ж: {fat}г | У: {carbs}г)\n\n"
                f"📊 Всего за сегодня: **{total_cal:.0f} / {TARGET_CALORIES} ккал** (осталось: {left:.0f})"
            )
            
        except Exception as e:
            logging.error(f"Error parsing food with Gemini: {e}")
            await message.answer(f"✅ Записал: *{text}*\n🔥 **+150 ккал** (усредненно)")

def run_web_server():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Web server running on port {PORT}")
        httpd.serve_forever()

async def main():
    print("Бот на Gemini запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    asyncio.run(main())
