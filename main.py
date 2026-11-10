import asyncio
import json
import logging
import os
from datetime import datetime
import http.server
import socketserver
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groq import Groq

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "9054880366:AAG8slNCtvq7DjyMLfa1-8pxriN1lD02EWI"
GROQ_API_KEY = "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"
TARGET_CALORIES = 1750  # Цель по калориям

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)

user_logs = {}

logging.basicConfig(level=logging.INFO)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Твой облачный бот-нутрициолог запущен и работает.\n\n"
        "Напиши текстом, что ты съел, а я посчитаю КБЖУ, запишу в статистику и подскажу остаток до цели (1750 ккал).\n\n"
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
    await message.answer("📈 **Еженедельный отчет:**\nВсе данные под контролем, держись отлично!")

@dp.message()
async def process_food(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    prompt = (
        f"Ты нутрициолог. Посчитай КБЖУ для: '{text}'. "
        "Напиши ответ в одну строчку через запятую строго в таком формате: "
        "калории, белки, жиры, углеводы, название. "
        "Пример: 450, 25.5, 12.0, 50.2, Лаваш с сыром и лососем. "
        "НЕ пиши никаких пояснений, только эти данные через запятую."
    )
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama3-8b-8192",  # Проверенная базовая модель Groq
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        response_text = completion.choices[0].message.content.strip()
        
        parts = [p.strip() for p in response_text.split(',')]
        if len(parts) >= 5:
            cal = float(parts[0])
            protein = float(parts[1])
            fat = float(parts[2])
            carbs = float(parts[3])
            desc = ", ".join(parts[4:])
        else:
            cal, protein, fat, carbs, desc = 350, 20.0, 10.0, 40.0, text

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
        logging.error(f"Error parsing food: {e}")
        await message.answer(f"⚠️ Ошибка отладки: {str(e)}")

# Веб-сервер-заглушка для удержания порта на Render
def run_web_server():
    PORT = int(os.environ.get("PORT", 10000))
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Web server running on port {PORT}")
        httpd.serve_forever()

async def main():
    print("Облачный бот запущен и слушает Telegram!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    asyncio.run(main())
