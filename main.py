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
        f"🔥 Калории: **{total_cal} ккал** (Осталось: {left} ккал до лимита)\n"
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
        f"Ты профессиональный спортивный нутрициолог. Проанализируй съеденное блюдо: '{text}'. "
        "Верни ответ СТРОГО в формате JSON без какого-либо дополнительного текста, используя только следующие ключи:\n"
        "{\n"
        '  "calories": 0,\n'
        '  "protein": 0.0,\n'
        '  "fat": 0.0,\n'
        '  "carbs": 0.0,\n'
        '  "description": "описание"\n'
        "}"
    )
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        response_text = completion.choices[0].message.content.strip()
        
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
            
        data = json.loads(response_text)
        
        today = datetime.now().strftime("%Y-%m-%d")
        if user_id not in user_logs:
            user_logs[user_id] = []
            
        user_logs[user_id].append({
            "date": today,
            "calories": float(data.get("calories", 0)),
            "protein": float(data.get("protein", 0)),
            "fat": float(data.get("fat", 0)),
            "carbs": float(data.get("carbs", 0))
        })
        
        today_logs = [l for l in user_logs[user_id] if l["date"] == today]
        total_cal = sum(item["calories"] for item in today_logs)
        left = TARGET_CALORIES - total_cal
        
        await message.answer(
            f"✅ Записал: *{data.get('description', text)}*\n\n"
            f"🔥 **+{data.get('calories', 0)} ккал** (Б: {data.get('protein', 0)}г | Ж: {data.get('fat', 0)}г | У: {data.get('carbs', 0)}г)\n\n"
            f"📊 Всего за сегодня: **{total_cal} / {TARGET_CALORIES} ккал** (осталось: {left})"
        )
        
    except Exception as e:
        logging.error(f"Error parsing food: {e}")
        await message.answer("Бро, не смог распознать формат. Попробуй написать чуть проще.")

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
    
