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

# Импортируем банк текстов
from texts import TEXTS_BANK

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

# --- База данных ---
conn = sqlite3.connect('leads.db', check_same_thread=False)
cursor_db = conn.cursor()
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
        timeline TEXT,
        budget TEXT
    )
''')
conn.commit()

# --- FSM ---
fsm_states = {}
def get_user_state(user_id): return fsm_states.get(user_id, {}).get("state", None)
def set_user_state(user_id, state):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}}
    fsm_states[user_id]["state"] = state
def get_user_data(user_id): return fsm_states.get(user_id, {}).get("data", {})
def set_user_data(user_id, data):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}}
    fsm_states[user_id]["data"] = data
def clear_user(user_id):
    if user_id in fsm_states: del fsm_states[user_id]

# --- Состояния ---
STATE_HOUSING = "housing"
STATE_ROOMS = "rooms"
STATE_AREA = "area"
STATE_REPAIR = "repair"
STATE_TIMELINE = "timeline"
STATE_CONFIRM = "confirm"
STATE_PHONE = "phone"
STATE_BUDGET = "budget"

# --- Клавиатура ---
def make_keyboard(buttons, per_row=2):
    kb = aiomax.buttons.KeyboardBuilder()
    row = []
    for text, payload in buttons:
        row.append(aiomax.buttons.CallbackButton(text, payload))
        if len(row) >= per_row:
            kb.row(*row)
            row = []
    if row: kb.row(*row)
    return kb

# ============================================================
# Главное меню и приветствие
# ============================================================

WELCOME_TEXT = (
    "👋 Здравствуйте! Меня зовут Иван. Я бот компании.\n\n" 
    "🟢 Безопасные материалы\n"
    "🟢 Защита от проблем после ремонта\n"
    "🟢 Долговечность: как в первый день\n"
    "🟢 Комфортная тишина\n"
    "🟢 Видеонаблюдение 24/7 (следите за ремонтом с телефона)\n\n"
    "Ответьте на пару вопросов и узнайте точную стоимость 👇"
)

WELCOME_KB = make_keyboard([
    ("✅ Узнать стоимость", "start_quiz"),
    ("📸 Портфолио", "portfolio"),
    ("💬 Отзывы", "reviews"),
    ("📞 Связаться", "contact"),
    ("🔥 Полезные советы", "useful_tips"),
], per_row=2)

BTN_BACK = ("🏠 В главное меню", "back_to_menu")
BTN_NEXT_TIP = ("➡️ Следующий совет", "next_tip")

# ============================================================
# Обработчики старта
# ============================================================

@bot.on_bot_start()
async def bot_start_handler(payload: aiomax.BotStartPayload):
    await payload.send(WELCOME_TEXT, keyboard=WELCOME_KB)

@bot.on_command("start")
async def cmd_start(ctx: aiomax.CommandContext):
    await ctx.reply(WELCOME_TEXT, keyboard=WELCOME_KB)

@bot.on_button_callback("back_to_menu")
async def back_to_menu_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    clear_user(user_id)
    await cb.answer(text=WELCOME_TEXT, keyboard=WELCOME_KB)

# ============================================================
# Банк текстов (Полезные советы)
# ============================================================

import random

@bot.on_button_callback("useful_tips")
async def useful_tips_handler(cb: aiomax.Callback):
    tip = random.choice(TEXTS_BANK)
    kb = make_keyboard([BTN_NEXT_TIP, BTN_BACK], per_row=1)
    await cb.answer(text=tip["text"], keyboard=kb)

@bot.on_button_callback("next_tip")
async def next_tip_handler(cb: aiomax.Callback):
    tip = random.choice(TEXTS_BANK)
    kb = make_keyboard([BTN_NEXT_TIP, BTN_BACK], per_row=1)
    await cb.answer(text=tip["text"], keyboard=kb)

# ============================================================
# Связаться с исполнителем
# ============================================================

@bot.on_button_callback("contact")
async def contact_handler(cb: aiomax.Callback):
    phone_number = "+79220392000"
    text = (
        "📞 **Связаться с исполнителем**\n\n"
        "Вы можете напрямую обсудить детали ремонта с нашим мастером:\n\n"
        "👤 **Имя:** Иван\n"
        f"📱 **Телефон:** [{phone_number}](tel:{phone_number})\n\n"
        "Нажмите на номер, чтобы позвонить с телефона 👆\n"
        "Или напишите нам прямо здесь, и мы ответим в течение 15 минут."
    )
    kb = make_keyboard([BTN_BACK], per_row=1)
    await cb.answer(text=text, keyboard=kb)

# ============================================================
# Отзывы
# ============================================================

@bot.on_button_callback("reviews")
async def reviews_handler(cb: aiomax.Callback):
    text = (
        "💬 **Отзывы и благодарственные письма**\n\n"
        "Мы гордимся нашей репутацией. Вот что пишут клиенты:\n\n"
        "«Сделали ремонт в двушке за 2 месяца. Всё чётко по срокам, мусор вывезли. "
        "Отдельное спасибо за помощь с выбором плитки!» — *Анна, ЖК «Светлый»*\n\n"
        "Выше вы можете посмотреть сканы благодарственных писем и отзывы."
    )
    folder_path = os.path.join("media", "reviews")
    attachments = []
    if os.path.exists(folder_path):
        files = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:10]
        for filename in files:
            try:
                attachment = await bot.upload_image(os.path.join(folder_path, filename))
                attachments.append(attachment)
            except Exception as e:
                print(f"Ошибка загрузки файла {filename}: {e}")
    kb = make_keyboard([BTN_BACK], per_row=1)
    if not attachments:
        await cb.answer(text=text + "\n\n*(Файлы писем временно недоступны)*", keyboard=kb)
    else:
        await cb.answer(text=text, attachments=attachments, keyboard=kb)

# ============================================================
# Портфолио
# ============================================================

@bot.on_button_callback("portfolio")
async def portfolio_handler(cb: aiomax.Callback):
    text = (
        "Показываем ремонты, которые мы сдали заказчикам за последние несколько дней 😊 как вам?\n\n"
        "Нажмите кнопку «Узнать стоимость» — посчитаем все индивидуально под вас, а еще промокод на скидку подарим 👇"
    )
    folder_path = os.path.join("media", "portfolio")
    attachments = []
    if os.path.exists(folder_path):
        files = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:10]
        for filename in files:
            try:
                attachment = await bot.upload_image(os.path.join(folder_path, filename))
                attachments.append(attachment)
            except Exception as e:
                print(f"Ошибка загрузки фото {filename}: {e}")
    kb = make_keyboard([("✅ Узнать стоимость", "start_quiz"), BTN_BACK], per_row=1)
    if not attachments:
        await cb.answer(text=text + "\n\n*(Фото временно недоступны)*", keyboard=kb)
    else:
        await cb.answer(text=text, attachments=attachments, keyboard=kb)

# ============================================================
# Квиз (Шаг 1-5)
# ============================================================

@bot.on_button_callback("start_quiz")
async def start_quiz(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_state(user_id, STATE_HOUSING)
    set_user_data(user_id, {})
    kb = make_keyboard([
        ("Новостройка", "housing_new"), ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"), ("Другое", "housing_other"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("housing_"))
async def step_housing(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {"housing_new": "Новостройка", "housing_secondary": "Вторичка", "housing_house": "Дом", "housing_other": "Другое"}
    value = mapping.get(cb.payload, "Другое")
    current = get_user_data(user_id)
    current["housing"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_ROOMS)
    kb = make_keyboard([
        ("Во всех", "rooms_all"), ("Гостиная", "rooms_living"), ("Спальня", "rooms_bedroom"),
        ("Детская", "rooms_kids"), ("Кухня", "rooms_kitchen"), ("Коридор", "rooms_hallway"),
        ("Ванная/туалет", "rooms_bathroom"), ("Балкон", "rooms_balcony"), ("Другое", "rooms_other"), BTN_BACK
    ], per_row=3)
    await cb.answer(text="Шаг 2. Сделать во всех комнатах или в отдельных?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("rooms_"))
async def step_rooms(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {
        "rooms_all": "Во всех", "rooms_living": "Гостиная", "rooms_bedroom": "Спальня",
        "rooms_kids": "Детская", "rooms_kitchen": "Кухня", "rooms_hallway": "Коридор",
        "rooms_bathroom": "Ванная/туалет", "rooms_balcony": "Балкон", "rooms_other": "Другое",
    }
    value = mapping.get(cb.payload, "Другое")
    current = get_user_data(user_id)
    current["rooms"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_AREA)
    kb = make_keyboard([("Не знаю", "area_unknown"), BTN_BACK], per_row=1)
    await cb.answer(text="Шаг 3. Напишите общую площадь помещений в м² (примерно):", keyboard=kb)

@bot.on_button_callback("area_unknown")
async def step_area_unknown(cb: aiomax.Callback):
    user_id = cb.user.user_id
    current = get_user_data(user_id)
    current["area"] = "Не знаю"
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_REPAIR)
    kb = make_keyboard([
        ("Капитальный", "repair_capital"), ("Косметический", "repair_cosmetic"),
        ("Дизайнерский", "repair_design"), ("Пока не знаю", "repair_unknown"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 4. Какой ремонт нужно сделать?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("repair_"))
async def step_repair(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {"repair_capital": "Капитальный", "repair_cosmetic": "Косметический", "repair_design": "Дизайнерский", "repair_unknown": "Пока не знаю"}
    value = mapping.get(cb.payload, "Пока не знаю")
    current = get_user_data(user_id)
    current["repair_type"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_TIMELINE)
    kb = make_keyboard([
        ("Этот месяц", "timeline_month"), ("1-2 месяца", "timeline_1_2"),
        ("3-4 месяца", "timeline_3_4"), ("5-6 месяцев", "timeline_5_6"),
        ("Пока не знаю", "timeline_unknown"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 5. Когда планируете начинать ремонт?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("timeline_"))
async def step_timeline(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {"timeline_month": "Этот месяц", "timeline_1_2": "1-2 месяца", "timeline_3_4": "3-4 месяца", "timeline_5_6": "5-6 месяцев", "timeline_unknown": "Пока не знаю"}
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
    kb = make_keyboard([("Всё верно", "confirm_yes"), ("Изменить", "confirm_edit"), BTN_BACK], per_row=2)
    await cb.answer(text=summary, keyboard=kb)

@bot.on_button_callback("confirm_yes")
async def confirm_yes(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_state(user_id, STATE_PHONE)
    kb = make_keyboard([BTN_BACK], per_row=1)
    await cb.answer(
        text=(
            "Отлично! Пожалуйста, отправьте ваш номер телефона в ответ на это сообщение. "
            "За номером закрепим индивидуальный промокод 🔥 48253 🔥 на скидку 10%.\n\n"
            "Напишите номер в формате: 79999999999"
        ),
        keyboard=kb
    )

@bot.on_button_callback("confirm_edit")
async def confirm_edit(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_data(user_id, {})
    set_user_state(user_id, STATE_HOUSING)
    kb = make_keyboard([
        ("Новостройка", "housing_new"), ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"), ("Другое", "housing_other"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

# ============================================================
# Шаг 6: Бюджет
# ============================================================

@bot.on_button_callback("budget_help")
async def budget_help_handler(cb: aiomax.Callback):
    text = (
        "Ремонт, который мы делаем, можно разделить на следующие категории 👇\n\n"
        "🔹 15-20.000 ₽ (чистовой ремонт без излишеств: ровно, аккуратно, практично)\n\n"
        "🔹 20-25.000 ₽ (качественный ремонт с продуманной логикой: хорошие материалы, удобная планировка)\n\n"
        "🔹 25-30.000 ₽ (как у дизайнеров: современные решения, скрытые элементы, визуальная целостность)\n\n"
        "🔹 от 30.000 ₽ (интерьер с характером: нестандартные решения, сложные узлы, дорогие материалы)\n\n"
        "**Уточните, какой у вас примерный бюджет на ремонт?** 👇"
    )
    kb = make_keyboard([
        ("до 15.000 ₽ / м²", "budget_15"),
        ("15-20.000 ₽ / м²", "budget_20"),
        ("20-25.000 ₽ / м²", "budget_25"),
        ("25-30.000 ₽ / м²", "budget_30"),
        ("от 30.000 ₽ / м²", "budget_50"),
        ("Не знаю", "budget_unknown"),
        BTN_BACK
    ], per_row=2)
    await cb.answer(text=text, keyboard=kb)

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
                ("Капитальный", "repair_capital"), ("Косметический", "repair_cosmetic"),
                ("Дизайнерский", "repair_design"), ("Пока не знаю", "repair_unknown"), BTN_BACK
            ], per_row=2)
            await message.reply("Шаг 4. Какой ремонт нужно сделать?", keyboard=kb)
        else:
            kb = make_keyboard([BTN_BACK], per_row=1)
            await message.reply("Пожалуйста, напишите число (например, 45) или выберите «Не знаю» 👇", keyboard=kb)
        return

    # --- Ввод телефона ---
    if state == STATE_PHONE:
        phone_clean = re.sub(r"\D", "", text) # Оставляем только цифры
        
        # Если ввели 10 цифр (без кода страны), добавляем 7
        if len(phone_clean) == 10:
            phone_clean = "7" + phone_clean
            
        # Проверяем: 11 цифр, начинается с 7 или 8
        if len(phone_clean) == 11 and (phone_clean.startswith("7") or phone_clean.startswith("8")):
            if phone_clean.startswith("8"):
                phone_clean = "7" + phone_clean[1:] # Меняем 8 на 7
                
            current = get_user_data(user_id)
            current["phone"] = phone_clean
            set_user_data(user_id, current)
            
            # Переходим к шагу бюджета
            set_user_state(user_id, STATE_BUDGET)
            
            text_budget = (
                "Евгений, последний вопрос. Чтобы не тратить ваше время - "
                "уточните, какой у вас примерный бюджет на ремонт?\n\n"
                "Так мы сможем сразу предложить то, что подходит именно вам 👇"
            )
            kb = make_keyboard([
                ("От чего зависит цена?", "budget_help"),
                ("до 15.000 ₽ / м²", "budget_15"),
                ("15-20.000 ₽ / м²", "budget_20"),
                ("20-25.000 ₽ / м²", "budget_25"),
                ("25-30.000 ₽ / м²", "budget_30"),
                ("от 30.000 ₽ / м²", "budget_50"),
                ("Не знаю", "budget_unknown"),
                BTN_BACK
            ], per_row=2)
            
            await message.reply(text_budget, keyboard=kb)
        else:
            kb = make_keyboard([BTN_BACK], per_row=1)
            await message.reply("Не удалось распознать номер. Напишите мобильный в формате: 89991234567", keyboard=kb)
        return

    button_states = [STATE_HOUSING, STATE_ROOMS, STATE_REPAIR, STATE_TIMELINE, STATE_CONFIRM, STATE_BUDGET]
    if state in button_states:
        kb = make_keyboard([BTN_BACK], per_row=1)
        await message.reply("Пожалуйста, выберите вариант из кнопок ниже 👇", keyboard=kb)
    elif state is None:
        await message.reply("Нажмите /start, чтобы начать 👇")

# ============================================================
# Обработка выбора бюджета (ЗАВЕРШЕНИЕ КВИЗА)
# ============================================================

@bot.on_button_callback(lambda d: d.payload.startswith("budget_"))
async def step_budget(cb: aiomax.Callback):
    user_id = cb.user.user_id
    
    mapping = {
        "budget_15": "до 15.000 ₽ / м²",
        "budget_20": "15-20.000 ₽ / м²",
        "budget_25": "20-25.000 ₽ / м²",
        "budget_30": "25-30.000 ₽ / м²",
        "budget_50": "от 30.000 ₽ / м²",
        "budget_unknown": "Не знаю"
    }
    value = mapping.get(cb.payload, "Не знаю")
    
    current = get_user_data(user_id)
    current["budget"] = value
    set_user_data(user_id, current)
    data = get_user_data(user_id)

    # Заявка админу
    admin_text = (
        f"🔔 Новая заявка на ремонт!\n\n"
        f"📞 Телефон: {data.get('phone', '—')}\n"
        f"🏠 Тип жилья: {data.get('housing', '—')}\n"
        f"🚪 Комнаты: {data.get('rooms', '—')}\n"
        f"📐 Площадь: {data.get('area', '—')} м²\n"
        f"🔨 Тип ремонта: {data.get('repair_type', '—')}\n"
        f"📅 Сроки: {data.get('timeline', '—')}\n"
        f"💰 Бюджет: {value}"
    )

    # Сохранение в БД
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor_db.execute('''
        INSERT INTO leads (date, user_id, phone, housing, rooms, area, repair_type, timeline, budget)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        current_time, user_id, data.get('phone', ''),
        data.get('housing', ''), data.get('rooms', ''),
        data.get('area', ''), data.get('repair_type', ''),
        data.get('timeline', ''), value
    ))
    conn.commit()

    # Отправка админу
    try:
        await bot.send_message(admin_text, user_id=ADMIN_ID)
    except Exception as e:
        print(f"Ошибка отправки администратору: {e}")

    # Ответ клиенту
    kb = make_keyboard([BTN_BACK], per_row=1)
    await cb.answer(
        text=(
            "Спасибо! Я уже получил ваши ответы и считаю стоимость.\n\n"
            "Мы свяжемся с вами в течение часа."
        ),
        keyboard=kb
    )
    clear_user(user_id)

# ============================================================
# КОМАНДА /export
# ============================================================

@bot.on_command("export")
async def export_leads(ctx: aiomax.CommandContext):
    if ctx.message.sender.user_id != ADMIN_ID:
        await ctx.reply("У вас нет прав для этой команды.")
        return

    cursor_db.execute("SELECT date, phone, housing, rooms, area, repair_type, timeline, budget FROM leads ORDER BY id DESC")
    rows = cursor_db.fetchall()

    if not rows:
        await ctx.reply("База данных пуста. Заявок пока нет.")
        return

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Дата', 'Телефон', 'Тип жилья', 'Комнаты', 'Площадь', 'Тип ремонта', 'Сроки', 'Бюджет'])
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
# Запуск
# ============================================================

from keep_alive import start_web_server

async def main():
    asyncio.create_task(start_web_server())
    logging.info("Запуск бота...")
    await bot.start_polling()
    await bot.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
📌 Что ещё стоит обновить в texts.py
Чтобы видеонаблюдение упоминалось не только в меню, но и в прогревающих текстах, я рекомендую добавить новый пункт в ваш файл texts.py. Откройте его и добавьте в конец списка TEXTS_BANK следующий текст:

python
    {
        "id": "camera_24_7",
        "title": "📹 Видеонаблюдение 24/7",
        "text": (
            "**Ремонт под вашим контролем 24/7**\n\n"
            "Мы знаем, как важно быть в курсе того, что происходит в вашей квартире. "
            "Поэтому во всех комнатах, где производится ремонт, мы устанавливаем видеокамеры.\n\n"
            "Вы можете в любой момент открыть телефон и посмотреть, как идут работы, "
            "какие материалы завезены, и как аккуратно работают мастера.\n\n"
            "Это не только дает спокойствие, но и гарантирует, что работа выполняется строго по технологии. "
            "Никаких «сюрпризов» и недоделок за вашей спиной."
        )
    }
После этого сохраните оба файла, сделайте Commit и Push в GitHub Desktop. Render перезапустит бота, и клиенты увидят новый пункт в меню и новую информацию в советах!

еще кружки уменьши
Чтобы кружки стали визуально меньше, нужно использовать другой символ. Желтые кружки (🟡) и зеленые (🟢) — это крупные эмодзи. Чтобы они выглядели как аккуратные маркеры списка, лучше заменить их на символ • (жирная точка) или маленький зеленый квадрат ▪️.

Давайте заменим их на маленькие зеленые квадраты ▪️ — они выглядят строго и аккуратно.

Вот обновленный блок WELCOME_TEXT в вашем коде. Найдите его и замените на этот:

python
WELCOME_TEXT = (
    "👋 Здравствуйте! Меня зовут Иван. Я бот компании.\n\n" 
    "▪️ Безопасные материалы\n"
    "▪️ Защита от проблем после ремонта\n"
    "▪️ Долговечность: как в первый день\n"
    "▪️ Комфортная тишина\n"
    "▪️ Видеонаблюдение 24/7 (следите за ремонтом с телефона)\n\n"
    "Ответьте на пару вопросов и узнайте точную стоимость 👇"
)
Если вам нужны именно зеленые точки, но маленькие, можно использовать обычный символ точки, но покрасить его в зеленый цвет с помощью HTML-кода (если мессенджер поддерживает Markdown/HTML). Но ▪️ — это самый надежный вариант, который точно отобразится как маленький аккуратный маркер.

После замены этого блока сохраните файл, сделайте Commit и Push в GitHub Desktop.

выведи обновленный код
Вот полный обновленный код bot.py с уменьшенными маркерами (▪️), новым приветствием и добавленным пунктом про видеонаблюдение.

python
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

# Импортируем банк текстов
from texts import TEXTS_BANK

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

# --- База данных ---
conn = sqlite3.connect('leads.db', check_same_thread=False)
cursor_db = conn.cursor()
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
        timeline TEXT,
        budget TEXT
    )
''')
conn.commit()

# --- FSM ---
fsm_states = {}
def get_user_state(user_id): return fsm_states.get(user_id, {}).get("state", None)
def set_user_state(user_id, state):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}}
    fsm_states[user_id]["state"] = state
def get_user_data(user_id): return fsm_states.get(user_id, {}).get("data", {})
def set_user_data(user_id, data):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}}
    fsm_states[user_id]["data"] = data
def clear_user(user_id):
    if user_id in fsm_states: del fsm_states[user_id]

# --- Состояния ---
STATE_HOUSING = "housing"
STATE_ROOMS = "rooms"
STATE_AREA = "area"
STATE_REPAIR = "repair"
STATE_TIMELINE = "timeline"
STATE_CONFIRM = "confirm"
STATE_PHONE = "phone"
STATE_BUDGET = "budget"

# --- Клавиатура ---
def make_keyboard(buttons, per_row=2):
    kb = aiomax.buttons.KeyboardBuilder()
    row = []
    for text, payload in buttons:
        row.append(aiomax.buttons.CallbackButton(text, payload))
        if len(row) >= per_row:
            kb.row(*row)
            row = []
    if row: kb.row(*row)
    return kb

# ============================================================
# Главное меню и приветствие
# ============================================================

WELCOME_TEXT = (
    "👋 Здравствуйте! Меня зовут Иван. Я бот компании.\n\n" 
    "▪️ Безопасные материалы\n"
    "▪️ Защита от проблем после ремонта\n"
    "▪️ Долговечность: как в первый день\n"
    "▪️ Комфортная тишина\n"
    "▪️ Видеонаблюдение 24/7 (следите за ремонтом с телефона)\n\n"
    "Ответьте на пару вопросов и узнайте точную стоимость 👇"
)

WELCOME_KB = make_keyboard([
    ("✅ Узнать стоимость", "start_quiz"),
    ("📸 Портфолио", "portfolio"),
    ("💬 Отзывы", "reviews"),
    ("📞 Связаться", "contact"),
    ("🔥 Полезные советы", "useful_tips"),
], per_row=2)

BTN_BACK = ("🏠 В главное меню", "back_to_menu")
BTN_NEXT_TIP = ("➡️ Следующий совет", "next_tip")

# ============================================================
# Обработчики старта
# ============================================================

@bot.on_bot_start()
async def bot_start_handler(payload: aiomax.BotStartPayload):
    await payload.send(WELCOME_TEXT, keyboard=WELCOME_KB)

@bot.on_command("start")
async def cmd_start(ctx: aiomax.CommandContext):
    await ctx.reply(WELCOME_TEXT, keyboard=WELCOME_KB)

@bot.on_button_callback("back_to_menu")
async def back_to_menu_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    clear_user(user_id)
    await cb.answer(text=WELCOME_TEXT, keyboard=WELCOME_KB)

# ============================================================
# Банк текстов (Полезные советы)
# ============================================================

import random

@bot.on_button_callback("useful_tips")
async def useful_tips_handler(cb: aiomax.Callback):
    tip = random.choice(TEXTS_BANK)
    kb = make_keyboard([BTN_NEXT_TIP, BTN_BACK], per_row=1)
    await cb.answer(text=tip["text"], keyboard=kb)

@bot.on_button_callback("next_tip")
async def next_tip_handler(cb: aiomax.Callback):
    tip = random.choice(TEXTS_BANK)
    kb = make_keyboard([BTN_NEXT_TIP, BTN_BACK], per_row=1)
    await cb.answer(text=tip["text"], keyboard=kb)

# ============================================================
# Связаться с исполнителем
# ============================================================

@bot.on_button_callback("contact")
async def contact_handler(cb: aiomax.Callback):
    phone_number = "+79220392000"
    text = (
        "📞 **Связаться с исполнителем**\n\n"
        "Вы можете напрямую обсудить детали ремонта с нашим мастером:\n\n"
        "👤 **Имя:** Иван\n"
        f"📱 **Телефон:** [{phone_number}](tel:{phone_number})\n\n"
        "Нажмите на номер, чтобы позвонить с телефона 👆\n"
        "Или напишите нам прямо здесь, и мы ответим в течение 15 минут."
    )
    kb = make_keyboard([BTN_BACK], per_row=1)
    await cb.answer(text=text, keyboard=kb)

# ============================================================
# Отзывы
# ============================================================

@bot.on_button_callback("reviews")
async def reviews_handler(cb: aiomax.Callback):
    text = (
        "💬 **Отзывы и благодарственные письма**\n\n"
        "Мы гордимся нашей репутацией. Вот что пишут клиенты:\n\n"
        "«Сделали ремонт в двушке за 2 месяца. Всё чётко по срокам, мусор вывезли. "
        "Отдельное спасибо за помощь с выбором плитки!» — *Анна, ЖК «Светлый»*\n\n"
        "Выше вы можете посмотреть сканы благодарственных писем и отзывы."
    )
    folder_path = os.path.join("media", "reviews")
    attachments = []
    if os.path.exists(folder_path):
        files = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:10]
        for filename in files:
            try:
                attachment = await bot.upload_image(os.path.join(folder_path, filename))
                attachments.append(attachment)
            except Exception as e:
                print(f"Ошибка загрузки файла {filename}: {e}")
    kb = make_keyboard([BTN_BACK], per_row=1)
    if not attachments:
        await cb.answer(text=text + "\n\n*(Файлы писем временно недоступны)*", keyboard=kb)
    else:
        await cb.answer(text=text, attachments=attachments, keyboard=kb)

# ============================================================
# Портфолио
# ============================================================

@bot.on_button_callback("portfolio")
async def portfolio_handler(cb: aiomax.Callback):
    text = (
        "Показываем ремонты, которые мы сдали заказчикам за последние несколько дней 😊 как вам?\n\n"
        "Нажмите кнопку «Узнать стоимость» — посчитаем все индивидуально под вас, а еще промокод на скидку подарим 👇"
    )
    folder_path = os.path.join("media", "portfolio")
    attachments = []
    if os.path.exists(folder_path):
        files = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith(('.jpg', '.jpeg', '.png'))][:10]
        for filename in files:
            try:
                attachment = await bot.upload_image(os.path.join(folder_path, filename))
                attachments.append(attachment)
            except Exception as e:
                print(f"Ошибка загрузки фото {filename}: {e}")
    kb = make_keyboard([("✅ Узнать стоимость", "start_quiz"), BTN_BACK], per_row=1)
    if not attachments:
        await cb.answer(text=text + "\n\n*(Фото временно недоступны)*", keyboard=kb)
    else:
        await cb.answer(text=text, attachments=attachments, keyboard=kb)

# ============================================================
# Квиз (Шаг 1-5)
# ============================================================

@bot.on_button_callback("start_quiz")
async def start_quiz(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_state(user_id, STATE_HOUSING)
    set_user_data(user_id, {})
    kb = make_keyboard([
        ("Новостройка", "housing_new"), ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"), ("Другое", "housing_other"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("housing_"))
async def step_housing(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {"housing_new": "Новостройка", "housing_secondary": "Вторичка", "housing_house": "Дом", "housing_other": "Другое"}
    value = mapping.get(cb.payload, "Другое")
    current = get_user_data(user_id)
    current["housing"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_ROOMS)
    kb = make_keyboard([
        ("Во всех", "rooms_all"), ("Гостиная", "rooms_living"), ("Спальня", "rooms_bedroom"),
        ("Детская", "rooms_kids"), ("Кухня", "rooms_kitchen"), ("Коридор", "rooms_hallway"),
        ("Ванная/туалет", "rooms_bathroom"), ("Балкон", "rooms_balcony"), ("Другое", "rooms_other"), BTN_BACK
    ], per_row=3)
    await cb.answer(text="Шаг 2. Сделать во всех комнатах или в отдельных?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("rooms_"))
async def step_rooms(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {
        "rooms_all": "Во всех", "rooms_living": "Гостиная", "rooms_bedroom": "Спальня",
        "rooms_kids": "Детская", "rooms_kitchen": "Кухня", "rooms_hallway": "Коридор",
        "rooms_bathroom": "Ванная/туалет", "rooms_balcony": "Балкон", "rooms_other": "Другое",
    }
    value = mapping.get(cb.payload, "Другое")
    current = get_user_data(user_id)
    current["rooms"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_AREA)
    kb = make_keyboard([("Не знаю", "area_unknown"), BTN_BACK], per_row=1)
    await cb.answer(text="Шаг 3. Напишите общую площадь помещений в м² (примерно):", keyboard=kb)

@bot.on_button_callback("area_unknown")
async def step_area_unknown(cb: aiomax.Callback):
    user_id = cb.user.user_id
    current = get_user_data(user_id)
    current["area"] = "Не знаю"
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_REPAIR)
    kb = make_keyboard([
        ("Капитальный", "repair_capital"), ("Косметический", "repair_cosmetic"),
        ("Дизайнерский", "repair_design"), ("Пока не знаю", "repair_unknown"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 4. Какой ремонт нужно сделать?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("repair_"))
async def step_repair(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {"repair_capital": "Капитальный", "repair_cosmetic": "Косметический", "repair_design": "Дизайнерский", "repair_unknown": "Пока не знаю"}
    value = mapping.get(cb.payload, "Пока не знаю")
    current = get_user_data(user_id)
    current["repair_type"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_TIMELINE)
    kb = make_keyboard([
        ("Этот месяц", "timeline_month"), ("1-2 месяца", "timeline_1_2"),
        ("3-4 месяца", "timeline_3_4"), ("5-6 месяцев", "timeline_5_6"),
        ("Пока не знаю", "timeline_unknown"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 5. Когда планируете начинать ремонт?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("timeline_"))
async def step_timeline(cb: aiomax.Callback):
    user_id = cb.user.user_id
    mapping = {"timeline_month": "Этот месяц", "timeline_1_2": "1-2 месяца", "timeline_3_4": "3-4 месяца", "timeline_5_6": "5-6 месяцев", "timeline_unknown": "Пока не знаю"}
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
    kb = make_keyboard([("Всё верно", "confirm_yes"), ("Изменить", "confirm_edit"), BTN_BACK], per_row=2)
    await cb.answer(text=summary, keyboard=kb)

@bot.on_button_callback("confirm_yes")
async def confirm_yes(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_state(user_id, STATE_PHONE)
    kb = make_keyboard([BTN_BACK], per_row=1)
    await cb.answer(
        text=(
            "Отлично! Пожалуйста, отправьте ваш номер телефона в ответ на это сообщение. "
            "За номером закрепим индивидуальный промокод 🔥 48253 🔥 на скидку 10%.\n\n"
            "Напишите номер в формате: 79999999999"
        ),
        keyboard=kb
    )

@bot.on_button_callback("confirm_edit")
async def confirm_edit(cb: aiomax.Callback):
    user_id = cb.user.user_id
    set_user_data(user_id, {})
    set_user_state(user_id, STATE_HOUSING)
    kb = make_keyboard([
        ("Новостройка", "housing_new"), ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"), ("Другое", "housing_other"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

# ============================================================
# Шаг 6: Бюджет
# ============================================================

@bot.on_button_callback("budget_help")
async def budget_help_handler(cb: aiomax.Callback):
    text = (
        "Ремонт, который мы делаем, можно разделить на следующие категории 👇\n\n"
        "🔹 15-20.000 ₽ (чистовой ремонт без излишеств: ровно, аккуратно, практично)\n\n"
        "🔹 20-25.000 ₽ (качественный ремонт с продуманной логикой: хорошие материалы, удобная планировка)\n\n"
        "🔹 25-30.000 ₽ (как у дизайнеров: современные решения, скрытые элементы, визуальная целостность)\n\n"
        "🔹 от 30.000 ₽ (интерьер с характером: нестандартные решения, сложные узлы, дорогие материалы)\n\n"
        "**Уточните, какой у вас примерный бюджет на ремонт?** 👇"
    )
    kb = make_keyboard([
        ("до 15.000 ₽ / м²", "budget_15"),
        ("15-20.000 ₽ / м²", "budget_20"),
        ("20-25.000 ₽ / м²", "budget_25"),
        ("25-30.000 ₽ / м²", "budget_30"),
        ("от 30.000 ₽ / м²", "budget_50"),
        ("Не знаю", "budget_unknown"),
        BTN_BACK
    ], per_row=2)
    await cb.answer(text=text, keyboard=kb)

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
                ("Капитальный", "repair_capital"), ("Косметический", "repair_cosmetic"),
                ("Дизайнерский", "repair_design"), ("Пока не знаю", "repair_unknown"), BTN_BACK
            ], per_row=2)
            await message.reply("Шаг 4. Какой ремонт нужно сделать?", keyboard=kb)
        else:
            kb = make_keyboard([BTN_BACK], per_row=1)
            await message.reply("Пожалуйста, напишите число (например, 45) или выберите «Не знаю» 👇", keyboard=kb)
        return

    # --- Ввод телефона ---
    if state == STATE_PHONE:
        phone_clean = re.sub(r"\D", "", text) # Оставляем только цифры
        
        # Если ввели 10 цифр (без кода страны), добавляем 7
        if len(phone_clean) == 10:
            phone_clean = "7" + phone_clean
            
        # Проверяем: 11 цифр, начинается с 7 или 8
        if len(phone_clean) == 11 and (phone_clean.startswith("7") or phone_clean.startswith("8")):
            if phone_clean.startswith("8"):
                phone_clean = "7" + phone_clean[1:] # Меняем 8 на 7
                
            current = get_user_data(user_id)
            current["phone"] = phone_clean
            set_user_data(user_id, current)
            
            # Переходим к шагу бюджета
            set_user_state(user_id, STATE_BUDGET)
            
            text_budget = (
                "Евгений, последний вопрос. Чтобы не тратить ваше время - "
                "уточните, какой у вас примерный бюджет на ремонт?\n\n"
                "Так мы сможем сразу предложить то, что подходит именно вам 👇"
            )
            kb = make_keyboard([
                ("От чего зависит цена?", "budget_help"),
                ("до 15.000 ₽ / м²", "budget_15"),
                ("15-20.000 ₽ / м²", "budget_20"),
                ("20-25.000 ₽ / м²", "budget_25"),
                ("25-30.000 ₽ / м²", "budget_30"),
                ("от 30.000 ₽ / м²", "budget_50"),
                ("Не знаю", "budget_unknown"),
                BTN_BACK
            ], per_row=2)
            
            await message.reply(text_budget, keyboard=kb)
        else:
            kb = make_keyboard([BTN_BACK], per_row=1)
            await message.reply("Не удалось распознать номер. Напишите мобильный в формате: 89991234567", keyboard=kb)
        return

    button_states = [STATE_HOUSING, STATE_ROOMS, STATE_REPAIR, STATE_TIMELINE, STATE_CONFIRM, STATE_BUDGET]
    if state in button_states:
        kb = make_keyboard([BTN_BACK], per_row=1)
        await message.reply("Пожалуйста, выберите вариант из кнопок ниже 👇", keyboard=kb)
    elif state is None:
        await message.reply("Нажмите /start, чтобы начать 👇")

# ============================================================
# Обработка выбора бюджета (ЗАВЕРШЕНИЕ КВИЗА)
# ============================================================

@bot.on_button_callback(lambda d: d.payload.startswith("budget_"))
async def step_budget(cb: aiomax.Callback):
    user_id = cb.user.user_id
    
    mapping = {
        "budget_15": "до 15.000 ₽ / м²",
        "budget_20": "15-20.000 ₽ / м²",
        "budget_25": "20-25.000 ₽ / м²",
        "budget_30": "25-30.000 ₽ / м²",
        "budget_50": "от 30.000 ₽ / м²",
        "budget_unknown": "Не знаю"
    }
    value = mapping.get(cb.payload, "Не знаю")
    
    current = get_user_data(user_id)
    current["budget"] = value
    set_user_data(user_id, current)
    data = get_user_data(user_id)

    # Заявка админу
    admin_text = (
        f"🔔 Новая заявка на ремонт!\n\n"
        f"📞 Телефон: {data.get('phone', '—')}\n"
        f"🏠 Тип жилья: {data.get('housing', '—')}\n"
        f"🚪 Комнаты: {data.get('rooms', '—')}\n"
        f"📐 Площадь: {data.get('area', '—')} м²\n"
        f"🔨 Тип ремонта: {data.get('repair_type', '—')}\n"
        f"📅 Сроки: {data.get('timeline', '—')}\n"
        f"💰 Бюджет: {value}"
    )

    # Сохранение в БД
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor_db.execute('''
        INSERT INTO leads (date, user_id, phone, housing, rooms, area, repair_type, timeline, budget)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        current_time, user_id, data.get('phone', ''),
        data.get('housing', ''), data.get('rooms', ''),
        data.get('area', ''), data.get('repair_type', ''),
        data.get('timeline', ''), value
    ))
    conn.commit()

    # Отправка админу
    try:
        await bot.send_message(admin_text, user_id=ADMIN_ID)
    except Exception as e:
        print(f"Ошибка отправки администратору: {e}")

    # Ответ клиенту
    kb = make_keyboard([BTN_BACK], per_row=1)
    await cb.answer(
        text=(
            "Спасибо! Я уже получил ваши ответы и считаю стоимость.\n\n"
            "Мы свяжемся с вами в течение часа."
        ),
        keyboard=kb
    )
    clear_user(user_id)

# ============================================================
# КОМАНДА /export
# ============================================================

@bot.on_command("export")
async def export_leads(ctx: aiomax.CommandContext):
    if ctx.message.sender.user_id != ADMIN_ID:
        await ctx.reply("У вас нет прав для этой команды.")
        return

    cursor_db.execute("SELECT date, phone, housing, rooms, area, repair_type, timeline, budget FROM leads ORDER BY id DESC")
    rows = cursor_db.fetchall()

    if not rows:
        await ctx.reply("База данных пуста. Заявок пока нет.")
        return

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Дата', 'Телефон', 'Тип жилья', 'Комнаты', 'Площадь', 'Тип ремонта', 'Сроки', 'Бюджет'])
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
# Запуск
# ============================================================

from keep_alive import start_web_server

async def main():
    asyncio.create_task(start_web_server())
    logging.info("Запуск бота...")
    await bot.start_polling()
    await bot.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())