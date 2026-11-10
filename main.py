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
        "Напиши текстом, что ты съел (например: *'Гречка отварная 210г и рыбная котлета 90г'*), "
        "а я посчитаю КБЖУ, запишу в статистику и подскажу остаток до цели (1750 ккал).\n\n"
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
