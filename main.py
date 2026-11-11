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

# --- РАСШИРЕННЫЙ ТОЧНЫЙ СПРАВОЧНИК (на 100г продукта) ---
def smart_fallback_calculate(text: str):
    text_lower = text.lower()
    
    match_weight = re.search(r'(\d+)\s*(?:г|гр|мл|шт)?', text_lower)
    weight = float(match_weight.group(1)) if match_weight else 100.0
    k = weight / 100.0  # коэффициент пересчета на массу

    # 1. МАСЛА И ЖИРЫ
    if any(w in text_lower for w in ['масло сливочное', 'масло']):
        cal, p, f, c = 717.0, 0.5, 81.0, 0.8
    elif any(w in text_lower for w in ['оливковое', 'подсолнечное', 'олия']):
        cal, p, f, c = 884.0, 0.0, 100.0, 0.0
    elif 'сало' in text_lower:
        cal, p, f, c = 797.0, 2.4, 89.0, 0.0

    # 2. СЫРЫ И МОЛОЧКА
    elif 'сулугуни' in text_lower:
        cal, p, f, c = 285.0, 20.5, 22.0, 0.0
    elif 'гауда' in text_lower:
        cal, p, f, c = 356.0, 24.9, 27.4, 2.2
    elif 'российский' in text_lower:
        cal, p, f, c = 363.0, 23.4, 29.5, 0.0
    elif 'плавленый' in text_lower:
        cal, p, f, c = 225.0, 10.0, 18.0, 4.0
    elif 'молоко 1%' in text_lower or 'молоко 1' in text_lower:
        cal, p, f, c = 42.0, 3.0, 1.0, 4.7
    elif 'молоко' in text_lower:
        cal, p, f, c = 60.0, 3.2, 3.2, 4.7
    elif any(w in text_lower for w in ['творог', 'кефир', 'йогурт']):
        cal, p, f, c = 85.0, 15.0, 3.0, 3.5

    # 3. КАШИ И БАКАЛЕЯ (в отварном виде)
    elif 'гречк' in text_lower:
        cal, p, f, c = 103.0, 3.6, 0.7, 20.5
    elif 'рис' in text_lower:
        cal, p, f, c = 116.0, 2.5, 0.5, 24.9
    elif 'кус-кус' in text_lower or 'кускус' in text_lower:
        cal, p, f, c = 112.0, 3.8, 0.2, 23.2
    elif 'чечевиц' in text_lower:
        cal, p, f, c = 116.0, 9.0, 0.4, 20.0
    elif 'овсянк' in text_lower:
        cal, p, f, c = 88.0, 3.0, 1.7, 15.0
    elif 'макарон' in text_lower or 'спагетти' in text_lower:
        cal, p, f, c = 110.0, 3.6, 1.2, 21.2
    elif 'булгур' in text_lower:
        cal, p, f, c = 83.0, 3.1, 0.2, 17.5

    # 4. ХЛЕБОБУЛОЧНЫЕ И СЛАДКОЕ
    elif 'хлеб черный' in text_lower or 'ржаной' in text_lower:
        cal, p, f, c = 205.0, 6.6, 1.2, 40.0
    elif 'хлеб белый' in text_lower or 'хлеб' in text_lower:
        cal, p, f, c = 265.0, 8.0, 3.2, 49.0
    elif 'булочк' in text_lower:
        cal, p, f, c = 320.0, 7.5, 8.0, 54.0
    elif 'печенье шоколадн' in text_lower or 'шоколадное' in text_lower:
        cal, p, f, c = 480.0, 6.0, 21.0, 65.0
    elif 'печенье' in text_lower:
        cal, p, f, c = 417.0, 7.5, 12.0, 69.0
    elif 'шоколад' in text_lower or 'конфет' in text_lower or 'сладк' in text_lower:
        cal, p, f, c = 515.0, 4.5, 28.0, 60.0

    # 5. СОУСЫ
    elif 'кетчуп' in text_lower:
        cal, p, f, c = 93.0, 1.0, 0.1, 23.0
    elif any(w in text_lower for w in ['майонез', 'соус сливочный', 'соус сырный']):
        cal, p, f, c = 450.0, 1.2, 47.0, 3.5
    elif 'соус' in text_lower:
        cal, p, f, c = 150.0, 1.5, 10.0, 12.0

    # 6. ОВОЩИ
    elif 'картошк' in text_lower or 'картофель' in text_lower:
        cal, p, f, c = 77.0, 2.0, 0.4, 16.3
    elif 'морков' in text_lower:
        cal, p, f, c = 35.0, 1.3, 0.1, 6.9
    elif 'капуст' in text_lower:
        cal, p, f, c = 27.0, 1.8, 0.1, 4.7
    elif 'помидор' in text_lower or 'томат' in text_lower:
        cal, p, f, c = 18.0, 0.9, 0.2, 3.9
    elif 'огурц' in text_lower:
        cal, p, f, c = 15.0, 0.8, 0.1, 2.8
    elif 'лук' in text_lower:
        cal, p, f, c = 41.0, 1.4, 0.2, 8.2
    elif 'чеснок' in text_lower:
        cal, p, f, c = 149.0, 6.5, 0.5, 29.9
    elif 'буряк' in text_lower or 'свекл' in text_lower:
        cal, p, f, c = 43.0, 1.5, 0.1, 8.8

    # 7. МЯСО И РЫБА
    elif any(w in text_lower for w in ['мяс', 'филе', 'куриц', 'говядин', 'рыб', 'лосось']):
        cal, p, f, c = 135.0, 21.0, 4.5, 0.0

    # ВСЕ ОСТАЛЬНОЕ УСРЕДНЕННОЕ
    else:
        cal, p, f, c = 150.0, 5.0, 5.0, 20.0

    return round(cal * k, 1), round(p * k, 1), round(f * k, 1), round(c * k, 1)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Бот на связи и полностью готов к работе.\n\n"
        "Пиши любую еду или вес, а я посчитаю КБЖУ!\n\n"
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
        cal, protein, fat, carbs = 150.0, 10.0, 5.0, 15.0
        source_badge = "🤖 Gemini API"
        
        try:
            try:
            prompt = (
                "Посчитай КБЖУ для продукта: "
                f"'{text}'. "
                "Напиши в ответ ТОЛЬКО 4 числа через пробел (калории, белки, жиры, углеводы). Больше ничего."
            )
            
            response = ai_client.models.generate_content(
                response = ai_client.models.generate_content(
                model="gemini-2.5-flash",  
                contents=prompt,
            )
            
            response_text = response.text.strip() if response and response.text else ""
            numbers = [float(num) for num in re.findall(r'\d+(?:\.\d+)?', response_text)]
            
            if len(numbers) >= 4:
                cal, protein, fat, carbs = numbers[0], numbers[1], numbers[2], numbers[3]
            else:
                raise ValueError(f"Ответ ИИ не содержит 4 чисел. Сырой текст: '{response_text}'")
                
        except Exception as e:
            logging.error(f"API Error: {e}")
            # Выведем точную ошибку в чат, чтобы увидеть причину
            await message.answer(f"⚠️ Ошибка Gemini: {str(e)}")
            cal, protein, fat, carbs = smart_fallback_calculate(text)
            source_badge = "📚 Справочник (fallback)"

        desc = text
        today = datetime.now().strftime("%Y-%m-%d")
        
        add_log_db(user_id, today, cal, protein, fat, carbs, desc)
        
        today_logs = get_today_logs_db(user_id, today)
        total_cal = sum(item["calories"] for item in today_logs)
        left = TARGET_CALORIES - total_cal
        
        await message.answer(
            f"✅ Записал: *{desc}* [{source_badge}]\n\n"
            f"🔥 **+{cal:.0f} ккал** (Б: {protein}г | Ж: {fat}г | У: {carbs}г)\n\n"
            f"📊 Всего за сегодня: **{total_cal:.0f} / {TARGET_CALORIES} ккал** (осталось: {left:.0f})"
        )

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
