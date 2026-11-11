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
from aiogram.exceptions import TelegramConflictError
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
