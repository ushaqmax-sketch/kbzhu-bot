import os
import sqlite3
import logging
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TARGET_CALORIES = 1750
PORT = int(os.environ.get("PORT", 8080))

if not TELEGRAM_TOKEN:
    raise ValueError("❌ Ошибка: Не задан TELEGRAM_TOKEN в переменных окружения!")

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
    'ножки копчен': (215.0, 19.0, 15.0, 0.0),
    'ножка копчен': (215.0, 19.0, 15.0, 0.0),
    'курица копчен': (195.0, 20.0, 12.0, 0.0),
    'голень куриц': (160.0, 18.0, 9.0, 0.0),
    'бедро куриц': (185.0, 17.0, 12.0, 0.0),
    'крыло куриц': (210.0, 18.0, 15.0, 0.0),
    'филе курин': (113.0, 23.6, 1.9, 0.4),
    'филе': (135.0, 23.0, 2.5, 0.0),
    'куриц': (135.0, 23.0, 2.5, 0.0),
    'масло сливочн': (717.0, 0.8, 81.0, 0.0),
    'масло оливков': (884.0, 0.0, 100.0, 0.0),
    'олия оливков': (884.0, 0.0, 100.0, 0.0),
    'масло подсолнечн': (899.0, 0.0, 99.9, 0.0),
    'олия подсолнечн': (899.0, 0.0, 99.9, 0.0),
    'олия': (899.0, 0.0, 99.9, 0.0),
    'масло': (884.0, 0.0, 100.0, 0.0),
    'сливки 10': (118.0, 3.0, 10.0, 4.0),
    'сливки 20': (206.0, 2.8, 20.0, 3.5),
    'сливки 30': (294.0, 2.4, 30.0, 3.2),
    'сливки': (206.0, 2.8, 20.0, 3.5),
    'молоко': (42.0, 3.2, 2.5, 4.7),
    'кефир': (50.0, 2.8, 2.5, 4.0),
    'творог': (101.0, 18.0, 2.0, 3.3),
    'сухарик': (380.0, 11.0, 8.0, 65.0),
    'рухвик': (380.0, 11.0, 8.0, 65.0),
    'снек': (450.0, 8.0, 18.0, 60.0),
    'джерк': (410.0, 40.0, 20.0, 10.0),
    'тунец в собственном соку': (96.0, 22.0, 1.0, 0.0),
    'тунец в олии': (190.0, 24.0, 10.0, 0.0),
    'тунец': (101.0, 23.0, 1.0, 0.0),
    'лосось': (142.0, 20.0, 6.0, 0.0),
    'семг': (202.0, 20.0, 13.0, 0.0),
    'минтай': (72.0, 16.0, 0.9, 0.0),
    'рыб': (110.0, 18.0, 4.0, 0.0),
    'сникерс': (485.0, 8.5, 23.0, 61.0),
    'твикс': (495.0, 4.9, 24.0, 65.0),
    'баунти': (466.0, 3.7, 26.0, 56.0),
    'шоколад': (546.0, 5.4, 35.3, 56.5),
    'яйцо варен': (155.0, 13.0, 11.0, 1.1),
    'яйц': (155.0, 13.0, 11.0, 1.1),
    'гречка варен': (103.0, 3.6, 0.7, 20.5),
    'рис варен': (116.0, 2.5, 0.5, 24.9),
    'овсянка варен': (88.0, 3.0, 1.7, 15.0),
    'булгур варен': (83.0, 3.1, 0.4, 17.5),
    'макароны варен': (110.0, 4.0, 1.2, 21.0),
    'гречк': (103.0, 3.6, 0.7, 20.5),
    'рис': (116.0, 2.5, 0.5, 24.9),
    'овсянк': (88.0, 3.0, 1.7, 15.0),
    'булгур': (83.0, 3.1, 0.4, 17.5),
    'макарон': (110.0, 4.0, 1.2, 21.0),
    'сыр тверд': (360.0, 26.0, 27.0, 0.0),
    'пармезан': (431.0, 38.0, 29.0, 0.0),
    'моцарелла': (280.0, 18.0, 22.0, 2.0),
    'сулугуни': (290.0, 22.0, 22.0, 1.5),
    'сыр плавлен': (250.0, 15.0, 20.0, 4.0),
    'сыр': (350.0, 25.0, 26.0, 1.3),
    'морков по-корейски': (135.0, 1.2, 8.5, 13.0),
    'морковь по корейски': (135.0, 1.2, 8.5, 13.0),
    'капуст по-корейски': (55.0, 1.5, 3.0, 6.0),
    'капуст': (27.0, 1.8, 0.1, 4.7),
    'буряк': (43.0, 1.5, 0.1, 8.8),
    'свекл': (43.0, 1.5, 0.1, 8.8),
    'картофел': (77.0, 2.0, 0.4, 17.0),
    'огурц': (15.0, 0.8, 0.1, 2.8),
    'помидор': (18.0, 0.9, 0.2, 3.9),
    'морков': (32.0, 1.3, 0.1, 6.9),
    'лук': (41.0, 1.4, 0.2, 8.2),
    'гриб': (30.0, 3.1, 0.5, 0.5),
    'шампиньон': (27.0, 4.3, 1.0, 0.1),
    'грибы жарен': (120.0, 5.0, 9.0, 2.0),
    'чай': (2.0, 0.0, 0.0, 0.5),
    'кофе': (3.0, 0.2, 0.0, 0.6),
    'эспрессо': (9.0, 0.1, 0.0, 1.7),
    'латте': (60.0, 3.0, 3.0, 5.0),
    'капучино': (55.0, 3.0, 3.0, 4.5),
    'индейк': (140.0, 21.0, 3.0, 0.0),
    'говядин': (187.0, 19.0, 12.0, 0.0),
    'свинин': (257.0, 16.0, 21.0, 0.0),
    'фарш свинин': (320.0, 15.0, 28.0, 0.0),
    'фарш говяж': (250.0, 17.0, 20.0, 0.0),
    'хлеб': (265.0, 9.0, 3.2, 49.0),
    'лаваш': (235.0, 8.0, 1.0, 48.0),
    'банан': (89.0, 1.1, 0.3, 22.8),
    'яблок': (47.0, 0.4, 0.4, 9.8),
}

def parse_single_item(item_text: str):
    item_text_lower = item_text.lower()
    match_weight = re.search(r'(\d+)\s*(?:г|гр|мл|шт)?', item_text_lower)
    weight = float(match_weight.group(1)) if match_weight else 100.0
    
    if 'шт' in item_text_lower and match_weight:
        weight = float(match_weight.group(1)) * 55.0
    elif ('чашк' in item_text_lower or 'стакан' in item_text_lower) and not match_weight:
        weight = 250.0

    k = weight / 100.0
    sorted_keys = sorted(FOOD_DATABASE.keys(), key=len, reverse=True)
    
    for key in sorted_keys:
        if key in item_text_lower:
            cal, p, f, c = FOOD_DATABASE[key]
            return round(cal * k, 1), round(p * k, 1), round(f * k, 1), round(c * k, 1), f"Справочник ({key})"
            
    return round(150.0 * k, 1), round(10.0 * k, 1), round(5.0 * k, 1), round(15.0 * k, 1), "Справочник (усреднено)"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Здорово, бро! Офлайн-бот КБЖУ запущен.\n\n"
        "Отправляй продукты по одному или списком с новой строки:\n"
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
        
    user_id = message.from_user.id
    text = message.text
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    total_cal, total_p, total_f, total_c = 0.0, 0.0, 0.0, 0.0
    badges = []
    
    for line in lines:
        cal, p, f, c, badge = parse_single_item(line)
        total_cal += cal
        total_p += p
        total_f += f
        total_c += c
        badges.append(badge)

    today = datetime.now().strftime("%Y-%m-%d")
    add_log_db(user_id, today, total_cal, total_p, total_f, total_c, text)
    
    today_logs = get_today_logs_db(user_id, today)
    sum_today_cal = sum(item["calories"] for item in today_logs)
    left = TARGET_CALORIES - sum_today_cal
    badge_str = ", ".join(set(badges))
    
    await message.answer(
        f"✅ Записал:\n_{text_escape(text)}_\n[{badge_str}]\n\n"
        f"🔥 **+{total_cal:.0f} ккал** (Б: {total_p:.1f}г | Ж: {total_f:.1f}г | У: {total_c:.1f}г)\n\n"
        f"📊 Всего за сегодня: **{sum_today_cal:.0f} / {TARGET_CALORIES} ккал** (осталось: {left:.0f})"
    )

def text_escape(text):
    return text.replace('_', '\\_').replace('*', '\\*')

async def on_startup(bot: Bot):
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        await bot.set_webhook(webhook_url)

def main():
    app = web.Application()
    dp.startup.register(on_startup)
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
