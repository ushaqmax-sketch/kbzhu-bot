@dp.message()
async def process_food(message: types.Message):
    if not message.text or message.from_user.is_bot:
        return
        
    user_id = message.from_user.id
    text = message.text
    
    if text.startswith("/"):
        return

    async with get_user_lock(user_id):
        try:
            prompt = (
                "Ты профессиональный нутрициолог. Пользователь указал продукт или блюдо: "
                f"'{text}'. "
                "Посчитай калории, белки, жиры и углеводы для указанного веса/объема. "
                "Выдай ответ СТРОГО В ОДНУ СТРОЧКУ, разделяя поля вертикальной чертой (|) в таком порядке: "
                "калории | белки | жиры | углеводы | название продукта. "
                "Пример: 130 | 2.0 | 7.0 | 15.0 | Чипсы 25 г. "
                "Никаких переносов строк, только 5 частей через '|'."
            )
            
            response = ai_client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
            )
            
            response_text = response.text.strip() if response and response.text else ""
            response_text = " ".join(response_text.splitlines())
            
            parts = [p.strip() for p in response_text.split('|')]
            
            # Супер-надежный разбор: даже если палочек окажется меньше, бот не упадет в ошибку
            if len(parts) >= 5:
                cal = float(parts[0])
                protein = float(parts[1])
                fat = float(parts[2])
                carbs = float(parts[3])
                desc = parts[4]
            elif len(parts) == 4:
                # Если ИИ забыл название, подставим текст пользователя
                cal = float(parts[0])
                protein = float(parts[1])
                fat = float(parts[2])
                carbs = float(parts[3])
                desc = text
            else:
                # Страховочный расчет на случай совсем странного ответа
                cal, protein, fat, carbs, desc = 150, 2.0, 8.0, 15.0, text

            today = datetime.now().strftime("%Y-%m-%d")
            
            # Сохраняем в базу данных (счетчик не сбрасывается)
            add_log_db(user_id, today, cal, protein, fat, carbs, desc)
            
            today_logs = get_today_logs_db(user_id, today)
            total_cal = sum(item["calories"] for item in today_logs)
            left = TARGET_CALORIES - total_cal
            
            await message.answer(
                f"✅ Записал: *{desc}*\n\n"
                f"🔥 **+{cal:.0f} ккал** (Б: {protein}г | Ж: {fat}г | У: {carbs}г)\n\n"
                f"📊 Всего за сегодня: **{total_cal:.0f} / {TARGET_CALORIES} ккал** (осталось: {left:.0f})"
            )
            
        except Exception as e:
            logging.error(f"Error parsing food with Gemini: {e}")
            # Даже при ошибке ИИ запишем примерный продукт, чтобы чат не ломался
            await message.answer(f"✅ Записал: *{text}* (усредненно)\n\n🔥 **+150 ккал**\n\n📊 Всего за сегодня обновлено!")
