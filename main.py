import os
import sqlite3
import logging
import requests
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TARGET_CALORIES = 1750

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Ошибка: Не заданы TELEGRAM_TOKEN или GEMINI_API_KEY в переменных окружения!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

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

FOOD_DATABASE = {
    'гречк': (103.0, 3.6, 0.7, 20.5),
    'рис': (116.0, 2.5, 0.5, 24.9),
    'овсянк': (88.0, 3.0, 1.7, 15.0),
    'куриц': (135.0, 23.0, 2.5, 0.0),
    'филе': (135.0, 23.0, 2.5, 0.0),
    'индейк': (140.0, 21.0, 3.0, 0.0),
    'говядин': (187.0, 19.0, 12.0, 0.0),
    'творог': (101.0, 18.0, 2.0, 3.3),
    'яйц': (155.0, 13.0, 11.0, 1.1),
    'молок': (42.0, 3.2, 2.5, 4.7),
    'сыр': (350.0, 25.0, 26.0, 1.3),
    'хлеб': (265.0, 9.0, 3.2, 49.0),
    'банан': (89.0, 1.1, 0.3, 22.8),
    'яблок': (47.0, 0.4, 0.4, 9.8),
    'картофел': (77.0, 2.0, 0.4, 17.0),
    'макарон': (110.0, 4.0, 1.2, 21.0),
}

def smart_dictionary_lookup(text: str):
    text_lower = text.lower()
    match_weight = re.search(r'(\d+)\s*(?:г|гр|мл|шт)?', text_lower)
    weight = float(match_weight.group(1)) if match_weight else 100.0
    
    if 'шт' in text_lower and match_weight:
        weight = float(match_weight.group(1)) * 55.0

    k = weight / 100.0
    
    for key, values in FOOD_DATABASE.items():
        if key in text_lower:
            cal, p, f, c = values
            return round(cal * k, 1), round(p * k, 1), round(f * k, 1), round(c * k, 1)
            
    return round(150.0 * k, 1), round(10.0 * k, 1), round(5.0 * k, 1), round(15.0 * k, 1)

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
    except Exception as e:
        print(f"Gemini request exception: {e}")
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Бот пересобран с нуля и готов к работе.\n\n"
        "Команды:\n"
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
        f"🔥 Калории: **{total_cal:.0f} ккал** (Осталось: {left:.0f})\n"
        f"🥩 Б: {total_p:.1f}г | 🥑 Ж: {total_f:.1f}г | 🍞 У: {total_c:.1f}г"
    )

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    clear_today_logs_db(user_id, today)
    await message.answer("🔄 **Дневник за сегодня сброшен!**")

@dp.message()
async def process_food(message: types.Message):
    if not message.text or message.from_user.is_bot or message.text.startswith("/"):
        return
        
    text = message.text
    source_badge = "🤖 Gemini API"
    
    prompt = f"Посчитай КБЖУ для продукта: '{text}'. Напиши в ответ ТОЛЬКО 4 числа через пробел: калории, белки, жиры, углеводы. Больше ни слова."
    ai_response = ask_gemini_rest(prompt)
    
    cal, protein, fat, carbs = 0, 0, 0, 0
    
    if ai_response:
        numbers = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', ai_response)]
        if len(numbers) >= 4:
            cal, protein, fat, carbs = numbers[0], numbers[1], numbers[2], numbers[3]
        else:
            source_badge = "📚 Справочник"
            cal, protein, fat, carbs = smart_dictionary_lookup(text)
    else:
        source_badge = "📚 Справочник (офлайн)"
        cal, protein, fat, carbs = smart_dictionary_lookup(text)

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
        print("Бот запущен!")
        await dp.start_polling(bot, skip_updates=True)
    asyncio.run(main())
