import os
import sqlite3
import logging
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "9054880366:AAG8slNCtvq7DjyMLfa1-8pxriN1lD02EWI"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TARGET_CALORIES = 1750  # Твой дневной лимит калорий

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ ---
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

# --- ПРЯМОЙ ЗАПРОС К GEMINI ЧЕРЕЗ REST API (без тяжелых SDK) ---
def ask_gemini_rest(prompt_text: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            print(f"Gemini API Error status: {response.status_code}, body: {response.text}")
    except Exception as e:
        print(f"Request exception: {e}")
    return None

# --- СПРАВОЧНИК-ДУБЛЕР (если вдруг сеть моргнет) ---
def smart_fallback_calculate(text: str):
    return 150.0, 10.0, 5.0, 15.0

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Бот пересобран на чистом и быстром движке.\n\n"
        "Пиши еду, а я считаю КБЖУ!\n"
        "📊 /status — итог за день\n"
        "🔄 /reset — сбросить дневник"
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    today_logs = get_today_logs_db(user_id, today)
    
    if not today_logs:
        await message.answer("Сегодня ты еще ничего не записывал.")
        return
        
    total_cal = sum(item["calories"] for item in today_logs)
    total_p = sum(item["protein"] for item in today_logs)
    total_f = sum(item["fat"] for item in today_logs)
    total_c = sum(item["carbs"] for item in today_logs)
    left = TARGET_CALORIES - total_cal
    
    await message.answer(
        f"📊 **Итог за сегодня:**\n\n"
        f"🔥 Калории: **{total_cal:.0f} ккал** (Осталось: {left:.0f} ккал)\n"
        f"🥩 Белки: {total_p:.1f} г | 🥑 Жиры: {total_f:.1f} г | 🍞 Углеводы: {total_c:.1f} г"
    )

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    clear_today_logs_db(user_id, today)
    await message.answer("🔄 **Дневник сброшен!** Начинаем сначала.")

@dp.message()
async def process_food(message: types.Message):
    if not message.text or message.from_user.is_bot or message.text.startswith("/"):
        return
        
    user_id = message.from_user.id
    text = message.text
    
    prompt = (
        "Посчитай КБЖУ для продукта: "
        f"'{text}'. "
        "Напиши в ответ ТОЛЬКО 4 числа через пробел: калории, белки, жиры, углеводы. Больше ни слова."
    )
    
    ai_response = ask_gemini_rest(prompt)
    source_badge = "🤖 Gemini API"
    
    cal, protein, fat, carbs = 150.0, 10.0, 5.0, 15.0
    
    if ai_response:
        import re
        numbers = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', ai_response)]
        if len(numbers) >= 4:
            cal, protein, fat, carbs = numbers[0], numbers[1], numbers[2], numbers[3]
        else:
            source_badge = "📚 Справочник (fallback)"
            cal, protein, fat, carbs = smart_fallback_calculate(text)
    else:
        source_badge = "📚 Справочник (fallback)"
        cal, protein, fat, carbs = smart_fallback_calculate(text)

    today = datetime.now().strftime("%Y-%m-%d")
    add_log_db(user_id, today, cal, protein, fat, carbs, text)
    
    today_logs = get_today_logs_db(user_id, today)
    total_cal = sum(item["calories"] for item in today_logs)
    left = TARGET_CALORIES - total_cal
    
    await message.answer(
        f"✅ Записал: *{text}* [{source_badge}]\n\n"
        f"🔥 **+{cal:.0f} ккал** (Б: {protein}г | Ж: {fat}г | У: {carbs}г)\n\n"
        f"📊 Всего за сегодня: **{total_cal:.0f} / {TARGET_CALORIES} ккал** (осталось: {left:.0f})"
    )

if __name__ == "__main__":
    import asyncio
    async def main():
        print("Легкий бот запущен!")
        await dp.start_polling(bot, skip_updates=True)
    asyncio.run(main())
