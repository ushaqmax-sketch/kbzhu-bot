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

# Расширенный офлайн-справочник (на 100 грамм продукта)
FOOD_DATABASE = {
    # Копчености и курица
    'ножки копчен': (215.0, 19.0, 15.0, 0.0),
    'ножка копчен': (215.0, 19.0, 15.0, 0.0),
    'курица копчен': (195.0, 20.0, 12.0, 0.0),
    'голень куриц': (160.0, 18.0, 9.0, 0.0),
    'бедро куриц': (185.0, 17.0, 12.0, 0.0),
    'крыло куриц': (210.0, 18.0, 15.0, 0.0),
    'филе курин': (113.0, 23.6, 1.9, 0.4),
    'филе': (135.0, 23.0, 2.5, 0.0),
    'куриц': (135.0, 23.0, 2.5, 0.0),
    
    # Масла и жиры
    'масло сливочн': (717.0, 0.8, 81.0, 0.0),
    'масло оливков': (884.0, 0.0, 100.0, 0.0),
    'олия оливков': (884.0, 0.0, 100.0, 0.0),
    'масло подсолнечн': (899.0, 0.0, 99.9, 0.0),
    'олия подсолнечн': (899.0, 0.0, 99.9, 0.0),
    'олия': (899.0, 0.0, 99.9, 0.0),
    'масло': (884.0, 0.0, 100.0, 0.0),
    
    # Молочка и сливки
    'сливки 10': (118.0, 3.0, 10.0, 4.0),
    'сливки 20': (206.0, 2.8, 20.0, 3.5),
    'сливки 30': (294.0, 2.4, 30.0, 3.2),
    'сливки': (206.0, 2.8, 20.0, 3.5),
    'молоко': (42.0, 3.2, 2.5, 4.7),
    'кефир': (50.0, 2.8, 2.5, 4.0),
    'творог': (101.0, 18.0, 2.0, 3.3),
    
    # Снеки, сухарики, джерки
    'сухарик': (380.0, 11.0, 8.0, 65.0),
    'рухвик': (380.0, 11.0
