# bot.py
import sqlite3
import asyncio
import re
import logging
import os
import csv
import io
import time
from datetime import datetime
from dotenv import load_dotenv
import aiomax
import psycopg2

# Импортируем банк текстов
from texts import TEXTS_BANK

# ============================================================
# Загрузка конфигурации
# ============================================================

load_dotenv(".env.max")

BOT_TOKEN = os.getenv("BOT_TOKEN")
_admin_raw = os.getenv("ADMIN_ID", "0").strip()
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or BOT_TOKEN == "пока_нет_токена":
    raise ValueError("Укажите реальный BOT_TOKEN в .env.max")
if not _admin_raw.isdigit():
    raise ValueError(f"ADMIN_ID должен быть числом, сейчас: '{_admin_raw}'")
if not DATABASE_URL:
    raise ValueError("Укажите DATABASE_URL в .env.max")
ADMIN_ID = int(_admin_raw)

# ============================================================
# Инициализация
# ============================================================

bot = aiomax.Bot(BOT_TOKEN, default_format="markdown", use_certificate=True)

# --- База данных (PostgreSQL / Supabase) ---
conn = psycopg2.connect(DATABASE_URL)
cursor_db = conn.cursor()

# --- FSM ---
fsm_states = {}

def update_user_activity(user_id):
    if user_id not in fsm_states:
        fsm_states[user_id] = {"state": None, "data": {}, "last_active": time.time()}
    else:
        fsm_states[user_id]["last_active"] = time.time()

def get_user_state(user_id): return fsm_states.get(user_id, {}).get("state", None)
def set_user_state(user_id, state):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}, "last_active": time.time()}
    fsm_states[user_id]["state"] = state
def get_user_data(user_id): return fsm_states.get(user_id, {}).get("data", {})
def set_user_data(user_id, data):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}, "last_active": time.time()}
    fsm_states[user_id]["data"] = data
def clear_user(user_id):
    if user_id in fsm_states: del fsm_states[user_id]

# --- Состояния ---
STATE_HOUSING = "housing"
STATE_ROOMS_MULTI = "rooms_multi" # Новое состояние для мультивыбора
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
    "Работая с нами вы получаете:\n"
    "➤ Безопасные материалы\n"
    "➤ Защита от проблем после ремонта\n"
    "➤ Долговечность: как в первый день\n"
    "➤ Комфортная тишина\n"
    "➤ Видеонаблюдение 24/7 (следите за ремонтом с телефона)\n\n"
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
    update_user_activity(user_id)
    clear_user(user_id)
    await cb.answer(text=WELCOME_TEXT, keyboard=WELCOME_KB)

# ============================================================
# Банк текстов (Полезные советы)
# ============================================================

import random

@bot.on_button_callback("useful_tips")
async def useful_tips_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    tip = random.choice(TEXTS_BANK)
    kb = make_keyboard([BTN_NEXT_TIP, BTN_BACK], per_row=1)
    await cb.answer(text=tip["text"], keyboard=kb)

@bot.on_button_callback("next_tip")
async def next_tip_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    tip = random.choice(TEXTS_BANK)
    kb = make_keyboard([BTN_NEXT_TIP, BTN_BACK], per_row=1)
    await cb.answer(text=tip["text"], keyboard=kb)

# ============================================================
# Связаться с исполнителем
# ============================================================

@bot.on_button_callback("contact")
async def contact_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
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
    user_id = cb.user.user_id
    update_user_activity(user_id)
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
    user_id = cb.user.user_id
    update_user_activity(user_id)
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
    update_user_activity(user_id)
    set_user_state(user_id, STATE_HOUSING)
    set_user_data(user_id, {"rooms_list": []}) # Инициализируем список комнат
    kb = make_keyboard([
        ("Новостройка", "housing_new"), ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"), ("Другое", "housing_other"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("housing_"))
async def step_housing(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    mapping = {"housing_new": "Новостройка", "housing_secondary": "Вторичка", "housing_house": "Дом", "housing_other": "Другое"}
    value = mapping.get(cb.payload, "Другое")
    current = get_user_data(user_id)
    current["housing"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_ROOMS_MULTI)
    
    # Клавиатура для мультивыбора
    kb = make_keyboard([
        ("Гостиная", "room_toggle_living"), ("Спальня", "room_toggle_bedroom"),
        ("Детская", "room_toggle_kids"), ("Кухня", "room_toggle_kitchen"),
        ("Коридор", "room_toggle_hallway"), ("Ванная/туалет", "room_toggle_bathroom"),
        ("Балкон", "room_toggle_balcony"), ("Другое", "room_toggle_other"),
        ("➡️ Далее", "rooms_done"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 2. Сделать во всех комнатах или в отдельных?\n\n*Нажимайте на комнаты, чтобы выбрать их (или несколько)*:", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("room_toggle_"))
async def toggle_room(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    room_code = cb.payload.replace("room_toggle_", "")
    
    mapping = {
        "living": "Гостиная", "bedroom": "Спальня", "kids": "Детская",
        "kitchen": "Кухня", "hallway": "Коридор", "bathroom": "Ванная/туалет",
        "balcony": "Балкон", "other": "Другое"
    }
    room_name = mapping.get(room_code, "Другое")
    
    current = get_user_data(user_id)
    rooms_list = current.get("rooms_list", [])
    
    if room_name in rooms_list:
        rooms_list.remove(room_name) # Если уже выбрана — убираем
    else:
        rooms_list.append(room_name) # Если нет — добавляем
        
    current["rooms_list"] = rooms_list
    set_user_data(user_id, current)
    
    # Обновляем клавиатуру (добавляем галочки к выбранным)
    buttons = []
    for code, name in mapping.items():
        prefix = "✅ " if name in rooms_list else ""
        buttons.append((f"{prefix}{name}", f"room_toggle_{code}"))
    
    buttons.append(("➡️ Далее", "rooms_done"))
    buttons.append(BTN_BACK)
    
    kb = make_keyboard(buttons, per_row=2)
    await cb.answer(text="Выберите комнаты (можно несколько):", keyboard=kb)

@bot.on_button_callback("rooms_done")
async def rooms_done(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    
    current = get_user_data(user_id)
    rooms_list = current.get("rooms_list", [])
    
    if not rooms_list:
        await cb.answer(text="Пожалуйста, выберите хотя бы одну комнату 👇")
        return
        
    current["rooms"] = ", ".join(rooms_list)
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_AREA)
    
    kb = make_keyboard([("Не знаю", "area_unknown"), BTN_BACK], per_row=1)
    await cb.answer(text="Шаг 3. Напишите общую площадь помещений в м² (примерно):", keyboard=kb)

@bot.on_button_callback("area_unknown")
async def step_area_unknown(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
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
    update_user_activity(user_id)
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
    update_user_activity(user_id)
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
    update_user_activity(user_id)
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
    update_user_activity(user_id)
    set_user_data(user_id, {"rooms_list": []})
    set_user_state(user_id, STATE_HOUSING)
    kb = make_keyboard([
        ("Новостройка", "housing_new"), ("Вторичка", "housing_secondary"),
        ("Дом", "housing_house"), ("Другое", "housing_other"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 1. Где нужно сделать ремонт?", keyboard=kb)

# ============================================================
# Шаг 6: Бюджет
# ============================================================

@bot.on_button_callback("help_price")
async def budget_help_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    text = (
        "⚠️ **Важно:** Мы беремся только за ремонт помещений целиком (комната, кухня, санузел). "
        "Мелкие работы мы не выполняем.\n\n"
        "Что входит в наши услуги (цены за работы, без учета материалов) 👇\n\n"
        "🔹 **Капитальный ремонт (от 15 000 до 25 000 ₽/м²)**:\n"
        "Демонтаж старой стяжки и обоев, замена коммуникаций, выравнивание стен и откосов, заливка новой стяжки и чистовая отделка.\n\n"
        "🔹 **Дизайнерский ремонт (от 25 000 ₽/м²)**:\n"
        "Сложные узлы, скрытые элементы, дорогие материалы, авторский надзор.\n\n"
        "**Уточните, какой у вас примерный бюджет на ремонт (за работы)?** 👇"
    )
    kb = make_keyboard([
        ("15-25.000 ₽ / м²", "budget_15_25"),
        ("от 25.000 ₽ / м²", "budget_25_plus"),
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
    update_user_activity(user_id)
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
        phone_clean = re.sub(r"\D", "", text)
        if len(phone_clean) == 10:
            phone_clean = "7" + phone_clean
            
        if len(phone_clean) == 11 and (phone_clean.startswith("7") or phone_clean.startswith("8")):
            if phone_clean.startswith("8"):
                phone_clean = "7" + phone_clean[1:]
                
            current = get_user_data(user_id)
            current["phone"] = phone_clean
            set_user_data(user_id, current)
            
            set_user_state(user_id, STATE_BUDGET)
            
            text_budget = (
                "Последний вопрос. Чтобы не тратить ваше время - "
                "уточните, какой у вас примерный бюджет на ремонт?\n\n"
                "Так мы сможем сразу предложить то, что подходит именно вам 👇"
            )
            kb = make_keyboard([
                ("От чего зависит цена?", "help_price"),
                ("15-25.000 ₽ / м²", "budget_15_25"),
                ("от 25.000 ₽ / м²", "budget_25_plus"),
                ("Не знаю", "budget_unknown"),
                BTN_BACK
            ], per_row=2)
            
            await message.reply(text_budget, keyboard=kb)
        else:
            kb = make_keyboard([BTN_BACK], per_row=1)
            await message.reply("Не удалось распознать номер. Напишите мобильный в формате: 89991234567", keyboard=kb)
        return

    button_states = [STATE_HOUSING, STATE_ROOMS_MULTI, STATE_REPAIR, STATE_TIMELINE, STATE_CONFIRM, STATE_BUDGET]
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
    update_user_activity(user_id)
    
    mapping = {
        "budget_15_25": "15-25.000 ₽ / м²",
        "budget_25_plus": "от 25.000 ₽ / м²",
        "budget_unknown": "Не знаю"
    }
    value = mapping.get(cb.payload, "Не знаю")
    
    current = get_user_data(user_id)
    current["budget"] = value
    set_user_data(user_id, current)
    data = get_user_data(user_id)

    admin_text = (
        f"🔔 Новая заявка на ремонт!\n\n"
        f"📞 Телефон: {data.get('phone', '—')}\n"
        f"🏠 Тип жилья: {data.get('