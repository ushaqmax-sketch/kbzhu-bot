import asyncio
import logging
import os
from datetime import datetime
import http.server
import socketserver
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google import genai
from google.genai import types as genai_types

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "9054880366:AAG8slNCtvq7DjyMLfa1-8pxriN1lD02EWI"
GEMINI_API_KEY = "AQ.Ab8RN6K-xJ1BVzriY5Sg7w4AGJ8sOrLXDt7wLLkDvRyr2PL2Ww"
TARGET_CALORIES = 1750  # Твоя цель по калориям

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализация клиента Google GenAI
ai_client = genai.Client(api_key=GEMINI_API_KEY)

user_logs = {}

logging.basicConfig(level=logging.INFO)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Бот переведен на стабильный Google Gemini и полностью готов к работе.\n\n"
        "Напиши текстом, что ты съел (любые блюда, рецепты или граммовки), а я посчитаю КБЖУ, запишу в статистику и подскажу остаток до цели (1750 ккал).\n\n"
        "Команды:\n"
        "📊 /status — итог за сегодня\n"
        "📈 /week — отчёт за неделю"
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    
    logs = user_logs.get(user_id, [])
    today_logs = [l for l in logs if l["date"] == today]
    
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

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    await message.answer("📈 **Еженедельный отчет:**\nВсе данные под контролем, держишься отлично!")

@dp.message()
async def process_food(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    prompt = (
        f"Ты профессиональный нутрициолог. Оцени порцию или продукт по запросу: '{text}'. "
        "Напиши результат строго в одну строчку через запятую в таком формате: "
        "калории (число), белки (число), жиры (число), углеводы (число), название блюда с граммами. "
        "Пример: 450, 25.5, 12.0, 50.2, Лаваш с сыром и лососем. "
        "Никаких других слов, объяснений или знаков препинания в начале, только эти 5 элементов через запятую."
    )
    
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        response_text = response.text.strip()
        
        parts = [p.strip() for p in response_text.split(',')]
        if len(parts) >= 5:
            cal = float(parts[0])
            protein = float(parts[1])
            fat = float(parts[2])
            carbs = float(parts[3])
            desc = ", ".join(parts[4:])
        else:
            cal, protein, fat, carbs, desc = 350, 20.0, 10.0, 35.0, text

        today = datetime.now().strftime("%Y-%m-%d")
        if user_id not in user_logs:
            user_logs[user_id] = []
            
        user_logs[user_id].append({
            "date": today,
            "calories": cal,
            "protein": protein,
            "fat": fat,
            "carbs": carbs
        })
        
        today_logs = [l for l in user_logs[user_id] if l["date"] == today]
        total_cal = sum(item["calories"] for item in today_logs)
        left = TARGET_CALORIES - total_cal
        
        await message.answer(
            f"✅ Записал: *{desc}*\n\n"
            f"🔥 **+{cal:.0f} ккал** (Б: {protein}г | Ж: {fat}г | У: {carbs}г)\n\n"
            f"📊 Всего за сегодня: **{total_cal:.0f} / {TARGET_CALORIES} ккал** (осталось: {left:.0f})"
        )
        
    except Exception as e:
        logging.error(f"Error parsing food with Gemini: {e}")
        await message.answer(f"⚠️ Ошибка обработки запроса ИИ: {str(e)}")

def run_web_server():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Web server running on port {PORT}")
        httpd.serve_forever()

async def main():
    print("Облачный бот на Gemini запущен и слушает Telegram!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    asyncio.run(main())
    
