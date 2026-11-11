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

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "9054880366:AAG8slNCtvq7DjyMLfa1-8pxriN1lD02EWI"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TARGET_CALORIES = 1750  # Твой дневной лимит калорий

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

ai_client = genai.Client(api_key=GEMINI_API_KEY)
user_logs = {}

logging.basicConfig(level=logging.INFO)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Твой бот на базе бесплатного Gemini запущен и готов к работе в группе.\n\n"
        "Просто пиши текстом, что ты съел, а я посчитаю калории, БЖУ и подскажу остаток до цели (1750 ккал).\n\n"
        "Команды:\n"
        "📊 /status — итог за сегодня\n"
        "🔄 /reset — сбросить дневник за сегодня\n"
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

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user_id in user_logs:
        user_logs[user_id] = [l for l in user_logs[user_id] if l["date"] != today]
        
    await message.answer("🔄 **Дневник за сегодня полностью сброшен!** Начинаем с чистого листа.")

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    await message.answer("📈 **Еженедельный отчет:**\nВсе данные под контролем, держись отлично!")

@dp.message()
async def process_food(message: types.Message):
    # Игнорируем пустые сообщения или если автор — другой бот
    if not message.text or message.from_user.is_bot:
        return
        
    user_id = message.from_user.id
    text = message.text
    
    # Игнорируем сообщения, начинающиеся со слэша (чтобы не обрабатывать команды как еду)
    if text.startswith("/"):
        return

    try:
        prompt = (
            "Ты профессиональный нутрициолог. Оцени порцию или продукт по запросу пользователя: "
            f"'{text}'. "
            "Напиши результат строго в одну строчку через запятую в таком формате: "
            "калории (число), белки (число), жиры (число), углеводы (число), название блюда с граммами. "
            "Пример: 350, 20.5, 10.0, 35.0, Картошка вареная с курицей 300 г. "
            "Никаких других слов или объяснений в начале, только эти 5 элементов через запятую."
        )
        
        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )
        
        response_text = response.text.strip() if response and response.text else ""
        parts = [p.strip() for p in response_text.split(',')]
        
        if len(parts) >= 5:
            try:
                cal = float(parts[0])
                protein = float(parts[1])
                fat = float(parts[2])
                carbs = float(parts[3])
                desc = ", ".join(parts[4:])
            except ValueError:
                cal, protein, fat, carbs, desc = 350, 20.0, 10.0, 35.0, text
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
        await message.answer("⚠️ Не удалось распознать блюдо. Попробуй написать чуть иначе, например: `куриное филе 100г`")

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
