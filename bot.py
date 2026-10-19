# bot.py
import sqlite3
import asyncio
import re
import logging
import os
import csv
import io
from datetime import datetime
from dotenv import load_dotenv
import aiomax

# ============================================================
# Загрузка конфигурации
# ============================================================

load_dotenv(".env.max")

BOT_TOKEN = os.getenv("BOT_TOKEN")
_admin_raw = os.getenv("ADMIN_ID", "0").strip()

if not BOT_TOKEN or BOT_TOKEN == "пока_нет_токена":
    raise ValueError("Укажите реальный BOT_TOKEN в .env.max")
if not _admin_raw.isdigit():
    raise ValueError(f"ADMIN_ID должен быть числом, сейчас: '{_admin_raw}'")
ADMIN_ID = int(_admin_raw)

# ============================================================
# Инициализация
# ============================================================

bot = aiomax.Bot(BOT_TOKEN, default_format="markdown", use_certificate=True)

# --- Настройка базы данных SQLite ---
# check_same_thread=False нужен, чтобы база работала в асинхронном коде
conn = sqlite3.connect('leads.db', check_same_thread=False)
cursor_db = conn.cursor()

# Создаем таблицу, если ее еще нет
cursor_db.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        user_id INTEGER,
        phone TEXT,
        housing TEXT,
        rooms TEXT,
        area TEXT,
        repair_type TEXT,
        timeline TEXT
    )
''')
conn.commit()
# ------------------------------------

# Вместо проблемного FSMStorage используем обычный словарь
fsm_states = {}

def get_user_state(user_id):
    return fsm_states.get(user_id, {}).get("state", None)

def set_user_state(user_id, state):
    if user_id not in fsm_states:
        fsm_states[user_id] = {"state": None, "data": {}}
    fsm_states[user_id]["state"] = state

def get_user_data(user_id):
    return fsm_states.get(user_id, {}).get("data", {})

def set_user_data(user_id, data):
    if user_id not in fsm_states:
        fsm_states[user_id] = {"state": None, "data": {}}
    fsm_states[user_id]["data"] = data

def clear_user(user_id):
    if user_id in fsm_states:
        del fsm_states[user_id]

# ============================================================
# Состояния
# ============================================================

STATE_HOUSING = "housing"
STATE_ROOMS = "rooms"
STATE_AREA = "area"
STATE_REPAIR = "repair"
STATE_TIMELINE = "timeline"
STATE_CONFIRM = "confirm"
STATE_PHONE = "phone"

# ============================================================
# Клавиатура
# ============================================================

def make_keyboard(buttons, per_row=2):
    kb = aiomax.buttons.KeyboardBuilder()
    row = []
    for text, payload in buttons:
        row.append(aiomax.buttons.CallbackButton(text, payload))
        if len(row) >= per_row:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb

# ============================================================
# /start
# ============================================================

@bot.on_command("start")
async def cmd_start(ctx: aiomax.CommandContext):
    text = (
        "👋 Здравствуйте! Я бот компании «Ремонт Под Ключ в Екатеринбурге».\n\n"
        "🟡 Безопасные материалы\n"
        "🟡 Защита от проблем после ремонта\n"
        "🟡 Долговечность: как в первый день\n"
        "🟡 Комфортная тишина\n\n"
        "Ответьте на пару вопросов и узнайте точную стоимость 👇"
    )
    kb = make_keyboard([
        ("✅ Узнать стоимость", "start_quiz"),
        ("📸 Фото", "photos"),
        ("💬 Отзывы", "reviews"),
    ], per_row=2)
    await ctx.reply(text, keyboard=kb)

# ============================================================
# Заглушки
# ============================================================

@bot.on_button_callback("photos")
async def photos_stub(cb: aiomax.Callback):
    await cb.answer(text="Раздел в разработке. Скоро здесь появятся наши работы!")

@bot.on_button_callback("reviews")
async def reviews_stub(cb: aiomax.Callback):
    await cb.answer(text="Раздел в разработке. Скоро здесь появятся наши работы!")

# ============================================================
# Шаг 1: старт квиза
# ============================================================

@bot.on_button_callback("start_quiz")
async def start_quiz(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_state(user_id, STATE_HOUSING)
    set_user_data(user_id, {})

    kb = make_keyboard([
        ("Новостройка", "housing_new"),
        ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"),
        ("Другое", "housing_other"),
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

# ============================================================
# Шаг 1 → Шаг 2
# ============================================================

@bot.on_button_callback(lambda d: d.payload.startswith("housing_"))
async def step_housing(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {
        "housing_new": "Новостройка",
        "housing_secondary": "Вторичка",
        "housing_house": "Дом",
        "housing_other": "Другое",
    }
    value = mapping.get(cb.payload, "Другое")

    current = get_user_data(user_id)
    current["housing"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_ROOMS)

    kb = make_keyboard([
        ("Во всех", "rooms_all"),
        ("Гостиная", "rooms_living"),
        ("Спальня", "rooms_bedroom"),
        ("Детская", "rooms_kids"),
        ("Кухня", "rooms_kitchen"),
        ("Коридор", "rooms_hallway"),
        ("Ванная/туалет", "rooms_bathroom"),
        ("Балкон", "rooms_balcony"),
        ("Другое", "rooms_other"),
    ], per_row=3)
    await cb.answer(text="Шаг 2. Сделать во всех комнатах или в отдельных?", keyboard=kb)

# ============================================================
# Шаг 2 → Шаг 3
# ============================================================

@bot.on_button_callback(lambda d: d.payload.startswith("rooms_"))
async def step_rooms(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {
        "rooms_all": "Во всех",
        "rooms_living": "Гостиная",
        "rooms_bedroom": "Спальня",
        "rooms_kids": "Детская",
        "rooms_kitchen": "Кухня",
        "rooms_hallway": "Коридор",
        "rooms_bathroom": "Ванная/туалет",
        "rooms_balcony": "Балкон",
        "rooms_other": "Другое",
    }
    value = mapping.get(cb.payload, "Другое")

    current = get_user_data(user_id)
    current["rooms"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_AREA)

    kb = make_keyboard([("Не знаю", "area_unknown")], per_row=1)
    await cb.answer(
        text="Шаг 3. Напишите общую площадь помещений в м² (примерно):",
        keyboard=kb
    )

# ============================================================
# Шаг 3 (кнопка «Не знаю») → Шаг 4
# ============================================================

@bot.on_button_callback("area_unknown")
async def step_area_unknown(cb: aiomax.Callback):
    user_id = cb.user.user_id
    current = get_user_data(user_id)
    current["area"] = "Не знаю"
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_REPAIR)

    kb = make_keyboard([
        ("Капитальный", "repair_capital"),
        ("Косметический", "repair_cosmetic"),
        ("Дизайнерский", "repair_design"),
        ("Пока не знаю", "repair_unknown"),
    ], per_row=2)
    await cb.answer(text="Шаг 4. Какой ремонт нужно сделать?", keyboard=kb)

# ============================================================
# Шаг 4 → Шаг 5
# ============================================================

@bot.on_button_callback(lambda d: d.payload.startswith("repair_"))
async def step_repair(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {
        "repair_capital": "Капитальный",
        "repair_cosmetic": "Косметический",
        "repair_design": "Дизайнерский",
        "repair_unknown": "Пока не знаю",
    }
    value = mapping.get(cb.payload, "Пока не знаю")

    current = get_user_data(user_id)
    current["repair_type"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_TIMELINE)

    kb = make_keyboard([
        ("Этот месяц", "timeline_month"),
        ("1-2 месяца", "timeline_1_2"),
        ("3-4 месяца", "timeline_3_4"),
        ("5-6 месяцев", "timeline_5_6"),
        ("Пока не знаю", "timeline_unknown"),
    ], per_row=2)
    await cb.answer(text="Шаг 5. Когда планируете начинать ремонт?", keyboard=kb)

# ============================================================
# Шаг 5 → Сводка
# ============================================================

@bot.on_button_callback(lambda d: d.payload.startswith("timeline_"))
async def step_timeline(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {
        "timeline_month": "Этот месяц",
        "timeline_1_2": "1-2 месяца",
        "timeline_3_4": "3-4 месяца",
        "timeline_5_6": "5-6 месяцев",
        "timeline_unknown": "Пока не знаю",
    }
    value = mapping.get(cb.payload, "Пока не знаю")

    current = get_user_data(user_id)
    current["timeline"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_CONFIRM)

    data = get_user_data(user_id)
    summary = (
        f"Проверьте:\n"
        f"Нужно сделать {data.get('repair_type', '—').lower()} "
        f"в {data.get('housing', '—').lower()} "
        f"({data.get('rooms', '—')}), "
        f"площадь: {data.get('area', '—')} м². "
        f"Начать ремонт: {value.lower()}.\n\n"
        f"Всё верно?"
    )
    kb = make_keyboard([
        ("Всё верно", "confirm_yes"),
        ("Изменить", "confirm_edit"),
    ], per_row=2)
    await cb.answer(text=summary, keyboard=kb)

# ============================================================
# Подтверждение
# ============================================================

@bot.on_button_callback("confirm_yes")
async def confirm_yes(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_state(user_id, STATE_PHONE)
    await cb.answer(
        text=(
            "Отлично! Пожалуйста, отправьте ваш номер телефона в ответ на это сообщение. "
            "За номером закрепим индивидуальный промокод 🔥 48253 🔥 на скидку 10%.\n\n"
            "Напишите номер в формате: 79999999999"
        )
    )

@bot.on_button_callback("confirm_edit")
async def confirm_edit(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_data(user_id, {})
    set_user_state(user_id, STATE_HOUSING)

    kb = make_keyboard([
        ("Новостройка", "housing_new"),
        ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"),
        ("Другое", "housing_other"),
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

# ============================================================
# Обработка текста (площадь и телефон)
# ============================================================

@bot.on_message()
async def handle_text(message: aiomax.Message):
    user_id = message.sender.user_id
    state = get_user_state(user_id)
    text = message.content if message.content else None

    if not text:
        return

    # --- Ввод площади ---
    if state == STATE_AREA:
        area_match = re.search(r"\d+", text)
        if area_match:
            current = get_user_data(user_id)
            current["area"] = area_match.group()
            set_user_data(user_id, current)
            set_user_state(user_id, STATE_REPAIR)

            kb = make_keyboard([
                ("Капитальный", "repair_capital"),
                ("Косметический", "repair_cosmetic"),
                ("Дизайнерский", "repair_design"),
                ("Пока не знаю", "repair_unknown"),
            ], per_row=2)
            await message.reply("Шаг 4. Какой ремонт нужно сделать?", keyboard=kb)
        else:
            await message.reply(
                "Пожалуйста, напишите число (например, 45) "
                "или выберите «Не знаю» 👇"
            )
        return

    # --- Ввод телефона ---
    if state == STATE_PHONE:
        phone_clean = re.sub(r"\D", "", text)
        if len(phone_clean) == 11 and phone_clean.startswith("7"):
            current = get_user_data(user_id)
            current["phone"] = phone_clean
            set_user_data(user_id, current)
            data = get_user_data(user_id)

            admin_text = (
                f"🔔 Новая заявка на ремонт!\n\n"
                f"📞 Телефон: {data.get('phone', '—')}\n"
                f"🏠 Тип жилья: {data.get('housing', '—')}\n"
                f"🚪 Комнаты: {data.get('rooms', '—')}\n"
                f"📐 Площадь: {data.get('area', '—')} м²\n"
                f"🔨 Тип ремонта: {data.get('repair_type', '—')}\n"
                f"📅 Сроки: {data.get('timeline', '—')}"
            )

            # --- СОХРАНЯЕМ В БАЗУ ДАННЫХ ---
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor_db.execute('''
                INSERT INTO leads (date, user_id, phone, housing, rooms, area, repair_type, timeline)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                current_time,
                user_id,
                data.get('phone', ''),
                data.get('housing', ''),
                data.get('rooms', ''),
                data.get('area', ''),
                data.get('repair_type', ''),
                data.get('timeline', '')
            ))
            conn.commit()
            # -------------------------------

            try:
                await bot.send_message(admin_text, user_id=ADMIN_ID)
            except Exception as e:
                print(f"Ошибка отправки администратору: {e}")

            await message.reply(
                "Спасибо! Я уже получил ваши ответы и считаю стоимость. "
                "Мы свяжемся с вами в течение 15 минут."
            )
            clear_user(user_id)
        else:
            await message.reply("Пожалуйста, напишите номер в формате: 79999999999 👇")
        return

    # --- Не по сценарию ---
    button_states = [STATE_HOUSING, STATE_ROOMS, STATE_REPAIR, STATE_TIMELINE, STATE_CONFIRM]
    if state in button_states:
        await message.reply("Пожалуйста, выберите вариант из кнопок ниже 👇")
    elif state is None:
        await message.reply("Напишите /start, чтобы начать 👇")


# ============================================================
# КОМАНДА /export (Выгрузка заявок в Excel/CSV)
# ============================================================

@bot.on_command("export")
async def export_leads(ctx: aiomax.CommandContext):
    # Проверка: только для админа
    if ctx.message.sender.user_id != ADMIN_ID:
        await ctx.reply("У вас нет прав для этой команды.")
        return

    # Достаем заявки из БД
    cursor_db.execute("SELECT date, phone, housing, rooms, area, repair_type, timeline FROM leads ORDER BY id DESC")
    rows = cursor_db.fetchall()

    if not rows:
        await ctx.reply("База данных пуста. Заявок пока нет.")
        return

    # Формируем CSV файл в памяти
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Заголовки
    writer.writerow(['Дата', 'Телефон', 'Тип жилья', 'Комнаты', 'Площадь', 'Тип ремонта', 'Сроки'])
    
    # Данные
    for row in rows:
        writer.writerow(row)

    # Кодируем в байты (utf-8-sig нужен для правильного открытия в Excel)
    csv_bytes = output.getvalue().encode('utf-8-sig')
    
    # Создаем файловый объект в памяти для отправки
    file_obj = io.BytesIO(csv_bytes)
    file_obj.name = "leads_export.csv" # Имя файла

    try:
        # 1. Загружаем файл на сервер MAX (обязательно указываем имя файла для BytesIO)
        attachment = await bot.upload_file(file_obj, filename="leads_export.csv")
        
        # 2. Отправляем сообщение с вложением
        await ctx.reply(
            text="📊 Выгрузка всех заявок из базы данных",
            attachments=attachment
        )
    except Exception as e:
        await ctx.reply(f"Ошибка при отправке файла: {e}\nПопробуем отправить текстом.")
        # Если файл не отправился, отправляем хотя бы текстом
        text_export = "\n".join([f"{r[0]} | {r[1]} | {r[2]}" for r in rows])
        await ctx.reply(text_export)

# ============================================================
# Запуск (асинхронный для Render + UptimeRobot)
# ============================================================

from keep_alive import start_web_server

async def main():
    # 1. Запускаем веб-сервер в фоне (для UptimeRobot)
    asyncio.create_task(start_web_server())
    
    # 2. Запускаем бота
    logging.info("Запуск бота...")
    await bot.start_polling()
    
    # Закрываем сессию после остановки polling (если потребуется)
    await bot.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())