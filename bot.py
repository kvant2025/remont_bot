            "💳 Также напоминаю, что у нас есть **отсрочка платежа от банка-партнера** — "
            "вы можете начать ремонт сейчас, а оплатить позже или в рассрочку.\n\n"
            "Мы свяжемся с вами в течение часа, чтобы согласовать удобное время для замера."
        ),
        keyboard=kb
    )
    # Сбрасываем состояние, но НЕ флаг greeted, чтобы бот мог общаться
    set_user_state(user_id, None)

# ============================================================
# КОМАНДА /export
# ============================================================

@bot.on_command("export")
async def export_leads(ctx: aiomax.CommandContext):
    if ctx.message.sender.user_id != ADMIN_ID:
        await ctx.reply("У вас нет прав для этой команды.")
        return

    cursor_db.execute("SELECT date, phone, housing, rooms, area, ceiling, repair_type, timeline, budget FROM leads ORDER BY id DESC")
    rows = cursor_db.fetchall()

    if not rows:
        await ctx.reply("База данных пуста. Заявок пока нет.")
        return

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Дата', 'Телефон', 'Тип жилья', 'Комнаты', 'Площади', 'Потолки', 'Тип ремонта', 'Сроки', 'Бюджет'])
    for row in rows:
        writer.writerow(row)

    csv_bytes = output.getvalue().encode('utf-8-sig')
    file_obj = io.BytesIO(csv_bytes)
    file_obj.name = "leads_export.csv"

    try:
        attachment = await bot.upload_file(file_obj, filename="leads_export.csv")
        await ctx.reply(text="📊 Выгрузка всех заявок из базы данных", attachments=attachment)
    except Exception as e:
        await ctx.reply(f"Ошибка при отправке файла: {e}\nПопробуем отправить текстом.")
        text_export = "\n".join([f"{r[0]} | {r[1]} | {r[2]}" for r in rows])
        await ctx.reply(text_export)

# ============================================================
# Фоновая проверка неактивных клиентов (Дожим)
# ============================================================

async def check_inactive_users():
    while True:
        await asyncio.sleep(60)
        current_time = time.time()
        
        for user_id, data in list(fsm_states.items()):
            state = data.get("state")
            last_active = data.get("last_active", current_time)
            reminders_sent = data.get("reminders_sent", 0)
            
            if state is not None and reminders_sent < 3:
                time_passed = current_time - last_active
                text = None
                attachments = []
                
                if time_passed > 900 and reminders_sent == 0:
                    text = (
                        "👋 Здравствуйте! Вы здесь?\n\n"
                        "Я вижу, вы начали расчет, но отвлеклись. "
                        "Вот фотографии ремонтов, которые мы сделали за последнее время 👇\n\n"
                        "Давайте продолжим — это займет всего пару минут."
                    )
                    folder_path = os.path.join("media", "portfolio")
                    if os.path.exists(folder_path):
                        files = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:5]
                        for filename in files:
                            try:
                                attachment = await bot.upload_image(os.path.join(folder_path, filename))
                                attachments.append(attachment)
                            except Exception as e:
                                print(f"Ошибка загрузки фото для дожима {filename}: {e}")

                elif time_passed > 7200 and reminders_sent == 1:
                    text = (
                        "⏳ Не тороплю, но напомню: расчет занимает 2 минуты.\n\n"
                        "Если вам удобнее, я могу просто прислать примерную смету на вашу площадь "
                        "или чек-лист «10 ошибок при ремонте». Продолжим? 👇"
                    )
                elif time_passed > 86400 and reminders_sent == 2:
                    text = (
                        "🔥 У меня для вас новость!\n\n"
                        "Ваш персональный промокод на скидку 10% всё еще действует. "
                        "Давайте я досчитаю вашу стоимость и пришлю варианты? 👇"
                    )

                if text:
                    try:
                        if attachments:
                            await bot.send_message(text, user_id=user_id, attachments=attachments)
                        else:
                            await bot.send_message(text, user_id=user_id)
                            
                        fsm_states[user_id]["reminders_sent"] = reminders_sent + 1
                        fsm_states[user_id]["last_active"] = current_time
                    except Exception as e:
                        print(f"Не удалось отправить напоминание {user_id}: {e}")

# ============================================================
# Запуск
# ============================================================

from keep_alive import start_web_server

async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(check_inactive_users())
    logging.info("Запуск бота...")
    await bot.start_polling()
    await bot.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())