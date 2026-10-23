# bot.py
import psycopg2
import asyncio
import re
import logging
import os
import csv
import io
import time
import random
from datetime import datetime
from dotenv import load_dotenv
import aiomax
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# Импортируем банк текстов и промпты
from texts import TEXTS_BANK
from prompts import REPAIR_CONSULTANT_PROMPT

# ============================================================
# Загрузка конфигурации
# ============================================================

load_dotenv(".env.max")

BOT_TOKEN = os.getenv("BOT_TOKEN")
_admin_raw = os.getenv("ADMIN_ID", "0").strip()
DATABASE_URL = os.getenv("DATABASE_URL")
GIGACHAT_KEY = os.getenv("GIGACHAT_KEY")

if not BOT_TOKEN or BOT_TOKEN == "пока_нет_токена":
    raise ValueError("Укажите реальный BOT_TOKEN в .env.max")
if not _admin_raw.isdigit():
    raise ValueError(f"ADMIN_ID должен быть числом, сейчас: '{_admin_raw}'")
if not DATABASE_URL:
    raise ValueError("Укажите DATABASE_URL в .env.max")
if not GIGACHAT_KEY:
    raise ValueError("Укажите GIGACHAT_KEY в .env.max")
ADMIN_ID = int(_admin_raw)

# ============================================================
# Инициализация
# ============================================================

bot = aiomax.Bot(BOT_TOKEN, default_format="markdown", use_certificate=True)

# --- База данных (PostgreSQL / Supabase) ---
conn = psycopg2.connect(DATABASE_URL)
cursor_db = conn.cursor()

# --- Инициализация GigaChat (Ultra 3.5) с таймаутом ---
giga = GigaChat(
    base_url="https://api.giga.chat/v1",
    credentials=GIGACHAT_KEY,
    scope="GIGACHAT_API_PERS",
    verify_ssl_certs=False,
    timeout=10
)

# --- FSM ---
fsm_states = {}

def update_user_activity(user_id):
    if user_id not in fsm_states:
        fsm_states[user_id] = {"state": None, "data": {}, "last_active": time.time(), "reminders_sent": 0, "greeted": False}
    else:
        fsm_states[user_id]["last_active"] = time.time()
        fsm_states[user_id]["reminders_sent"] = 0

def get_user_state(user_id): return fsm_states.get(user_id, {}).get("state", None)
def set_user_state(user_id, state):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}, "last_active": time.time(), "reminders_sent": 0, "greeted": False}
    fsm_states[user_id]["state"] = state
def get_user_data(user_id): return fsm_states.get(user_id, {}).get("data", {})
def set_user_data(user_id, data):
    if user_id not in fsm_states: fsm_states[user_id] = {"state": None, "data": {}, "last_active": time.time(), "reminders_sent": 0, "greeted": False}
    fsm_states[user_id]["data"] = data
def clear_user(user_id):
    if user_id in fsm_states: del fsm_states[user_id]

# --- Состояния ---
STATE_HOUSING = "housing"
STATE_ROOMS_MULTI = "rooms_multi" 
STATE_ROOM_AREA = "room_area" 
STATE_CEILING = "ceiling"
STATE_REPAIR = "repair"
STATE_TIMELINE = "timeline"
STATE_CONFIRM = "confirm"
STATE_BUDGET = "budget"
STATE_CONTACT_METHOD = "contact_method"
STATE_PHONE = "phone"

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
# Функция запроса к GigaChat
# ============================================================

def ask_gigachat_ultra(user_text: str) -> str:
    """Отправляет запрос к GigaChat 3 Ultra, используя промпт из prompts.py."""
    chat = Chat(
        model="GigaChat-3-Ultra",
        messages=[
            Messages(role=MessagesRole.SYSTEM, content=REPAIR_CONSULTANT_PROMPT),
            Messages(role=MessagesRole.USER, content=user_text)
        ]
    )
    response = giga.chat(chat)
    return response.choices[0].message.content

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
    "➤ Видеонаблюдение 24/7 (следите за ремонтом с телефона)\n"
    "➤ 💳 **Отсрочка платежа от банка-партнера!**\n\n"
    "Ответьте на пару вопросов и узнайте точную стоимость 👇"
)

WELCOME_KB = make_keyboard([
    ("✅ Узнать стоимость", "start_quiz"),
    ("📸 Портфолио", "portfolio"),
    ("💬 Отзывы", "reviews"),
    ("📞 Контакты", "contact"),
    ("🔥 Полезные советы", "useful_tips"),
], per_row=2)

BTN_BACK = ("🏠 В главное меню", "back_to_menu")
BTN_PREV = ("⬅️ Назад", "go_back")
BTN_NEXT_TIP = ("➡️ Следующий совет", "next_tip")
BTN_UNKNOWN_AREA = ("Не знаю", "area_unknown")

# ============================================================
# Обработчики старта
# ============================================================

@bot.on_bot_start()
async def bot_start_handler(payload: aiomax.BotStartPayload):
    user_id = payload.user.id
    # Сбрасываем флаг приветствия, чтобы показать меню
    if user_id in fsm_states:
        fsm_states[user_id]["greeted"] = False
    await payload.send(WELCOME_TEXT, keyboard=WELCOME_KB)

@bot.on_command("start")
async def cmd_start(ctx: aiomax.CommandContext):
    user_id = ctx.message.sender.user_id
    update_user_activity(user_id)
    
    # Сбрасываем флаг, чтобы показать меню при команде /start
    current = fsm_states.get(user_id, {})
    current["greeted"] = False
    if user_id not in fsm_states: fsm_states[user_id] = current
    else: fsm_states[user_id]["greeted"] = False
    
    await ctx.reply(WELCOME_TEXT, keyboard=WELCOME_KB)

@bot.on_button_callback("back_to_menu")
async def back_to_menu_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    # Сбрасываем сессию, чтобы при следующем сообщении показать меню
    clear_user(user_id)
    await cb.answer(text=WELCOME_TEXT, keyboard=WELCOME_KB)

# ============================================================
# Кнопка "Назад" (Универсальная)
# ============================================================

@bot.on_button_callback("go_back")
async def go_back_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    state = get_user_state(user_id)
    
    if state == STATE_CONTACT_METHOD:
        set_user_state(user_id, STATE_BUDGET)
        text = (
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
        await cb.answer(text=text, keyboard=kb)
        
    elif state == STATE_PHONE:
        set_user_state(user_id, STATE_CONTACT_METHOD)
        text = (
            "Отлично! Я уже получил все ваши ответы и считаю стоимость.\n\n"
            "Выберите, куда вам удобнее получить расчет и несгораемую скидку на работы 10%? 👇"
        )
        kb = make_keyboard([
            ("MAX", "contact_max"),
            ("Telegram", "contact_telegram"),
            ("WhatsApp", "contact_whatsapp"),
            ("Позвоните", "contact_call"),
            BTN_BACK
        ], per_row=2)
        await cb.answer(text=text, keyboard=kb)
    
    else:
        clear_user(user_id)
        await cb.answer(text=WELCOME_TEXT, keyboard=WELCOME_KB)

# ============================================================
# Банк текстов (Полезные советы)
# ============================================================

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
# Контакты
# ============================================================

@bot.on_button_callback("contact")
async def contact_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    phone_number = "+79220392000"
    email = "79220392000@yandex.ru"
    
    text = (
        "📞 **Контакты**\n\n"
        "Вы можете напрямую обсудить детали ремонта с нашим мастером:\n\n"
        "👤 **Имя:** Евгений\n"
        f"📱 **Телефон:** [{phone_number}](tel:{phone_number})\n\n"
        f"✉️ **Почта:** {email}\n\n"
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
# Квиз (Шаг 1-6)
# ============================================================

@bot.on_button_callback("start_quiz")
async def start_quiz(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    set_user_state(user_id, STATE_HOUSING)
    set_user_data(user_id, {"rooms_list": []}) 
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
    
    kb = make_keyboard([
        ("Гостиная", "room_toggle_living"), ("Спальня", "room_toggle_bedroom"),
        ("Детская", "room_toggle_kids"), ("Кухня", "room_toggle_kitchen"),
        ("Коридор", "room_toggle_hallway"), ("Ванная/туалет", "room_toggle_bathroom"),
        ("Балкон", "room_toggle_balcony"), ("Другое", "room_toggle_other"),
        ("➡️ Далее", "rooms_done"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 2. Сделать во всех комнатах или в отдельных?\n\n*Нажимайте на комнаты, чтобы выбрать их (можно несколько)*:", keyboard=kb)

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
        rooms_list.remove(room_name)
    else:
        rooms_list.append(room_name)
        
    current["rooms_list"] = rooms_list
    set_user_data(user_id, current)
    
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
    current["rooms_to_process"] = list(rooms_list)
    current["areas"] = {}
    set_user_data(user_id, current)
    
    set_user_state(user_id, STATE_ROOM_AREA)
    
    room = rooms_list[0]
    kb = make_keyboard([BTN_UNKNOWN_AREA, BTN_BACK], per_row=1)
    await cb.answer(text=f"Шаг 3. Какая площадь у комнаты **{room}**? (в м²)", keyboard=kb)

@bot.on_button_callback("area_unknown")
async def step_area_unknown(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    
    current = get_user_data(user_id)
    rooms_to_process = current.get("rooms_to_process", [])
    
    if rooms_to_process:
        current_room = rooms_to_process[0]
        areas = current.get("areas", {})
        areas[current_room] = "Не знаю"
        current["areas"] = areas
        current["rooms_to_process"] = rooms_to_process[1:]
        set_user_data(user_id, current)
    
    if current["rooms_to_process"]:
        next_room = current["rooms_to_process"][0]
        kb = make_keyboard([BTN_UNKNOWN_AREA, BTN_BACK], per_row=1)
        await cb.answer(text=f"Какая площадь у комнаты **{next_room}**? (в м²)", keyboard=kb)
    else:
        set_user_state(user_id, STATE_CEILING)
        kb = make_keyboard([
            ("До 2.7 м (стандарт)", "ceiling_27"),
            ("2.7 - 3.2 м", "ceiling_32"),
            ("Выше 3.2 м", "ceiling_high"),
            ("Не знаю", "ceiling_unknown"),
            BTN_BACK
        ], per_row=2)
        await cb.answer(text="Шаг 4. Какая высота потолков в помещении?", keyboard=kb)

@bot.on_button_callback(lambda d: d.payload.startswith("ceiling_"))
async def step_ceiling(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    
    mapping = {
        "ceiling_27": "До 2.7 м",
        "ceiling_32": "2.7 - 3.2 м",
        "ceiling_high": "Выше 3.2 м",
        "ceiling_unknown": "Не знаю"
    }
    value = mapping.get(cb.payload, "Не знаю")
    
    current = get_user_data(user_id)
    current["ceiling"] = value
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_REPAIR)
    
    kb = make_keyboard([
        ("Капитальный", "repair_capital"), ("Косметический", "repair_cosmetic"),
        ("Дизайнерский", "repair_design"), ("Пока не знаю", "repair_unknown"), BTN_BACK
    ], per_row=2)
    await cb.answer(text="Шаг 5. Какой ремонт нужно сделать?", keyboard=kb)

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
    await cb.answer(text="Шаг 6. Когда планируете начинать ремонт?", keyboard=kb)

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
    
    areas_dict = data.get("areas", {})
    areas_str = ", ".join([f"{room}: {area} м²" for room, area in areas_dict.items()])
    
    summary = (
        f"Проверьте:\n"
        f"Нужно сделать {data.get('repair_type', '—').lower()} "
        f"в {data.get('housing', '—').lower()} "
        f"({data.get('rooms', '—')}). "
        f"Площади: {areas_str}. "
        f"Высота потолков: {data.get('ceiling', '—')}. "
        f"Начать ремонт: {value.lower()}.\n\n"
        f"Всё верно?"
    )
    kb = make_keyboard([("Всё верно", "confirm_yes"), ("Изменить", "confirm_edit"), BTN_BACK], per_row=2)
    await cb.answer(text=summary, keyboard=kb)

# ============================================================
# Обработка ПОДТВЕРЖДЕНИЯ
# ============================================================

@bot.on_button_callback("confirm_yes")
async def confirm_yes(cb: aiomax.Callback):
    user_id = cb.user.user_id
    update_user_activity(user_id)
    
    set_user_state(user_id, STATE_BUDGET)
    
    text = (
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
    
    await cb.answer(text=text, keyboard=kb)

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
# Шаг 7: Бюджет
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

@bot.on_button_callback(lambda d: d.payload.startswith("budget_") and d.payload != "budget_help")
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
    
    set_user_state(user_id, STATE_CONTACT_METHOD)
    
    text = (
        "Отлично! Я уже получил все ваши ответы и считаю стоимость.\n\n"
        "Выберите, куда вам удобнее получить расчет и несгораемую скидку на работы 10%? 👇"
    )
    kb = make_keyboard([
        ("MAX", "contact_max"),
        ("Telegram", "contact_telegram"),
        ("WhatsApp", "contact_whatsapp"),
        ("Позвоните", "contact_call"),
        BTN_PREV
    ], per_row=2)
    
    await cb.answer(text=text, keyboard=kb)

# ============================================================
# Обработка выбора способа связи
# ============================================================

@bot.on_button_callback("contact_max")
async def contact_max_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    current = get_user_data(user_id)
    current["contact_method"] = "MAX"
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_PHONE)
    
    await cb.answer(
        text=(
            "Отлично! Оставьте ваш номер телефона в формате **79999999999**, "
            "напишите ваш ник в формате **@ваш_ник** или просто введите ваше имя, чтобы менеджер мог связаться с вами 👇"
        ),
        keyboard=make_keyboard([BTN_PREV], per_row=1)
    )

@bot.on_button_callback("contact_telegram")
async def contact_telegram_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    current = get_user_data(user_id)
    current["contact_method"] = "Telegram"
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_PHONE)
    
    await cb.answer(
        text=(
            "Отлично! Оставьте ваш номер телефона в формате **79999999999**, "
            "напишите ваш ник в формате **@ваш_ник** или просто введите ваше имя, чтобы менеджер мог связаться с вами 👇"
        ),
        keyboard=make_keyboard([BTN_PREV], per_row=1)
    )

@bot.on_button_callback("contact_whatsapp")
async def contact_whatsapp_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    current = get_user_data(user_id)
    current["contact_method"] = "WhatsApp"
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_PHONE)
    
    await cb.answer(
        text=(
            "Отлично! Оставьте ваш номер телефона в формате **79999999999**, "
            "чтобы менеджер мог связаться с вами в WhatsApp 👇"
        ),
        keyboard=make_keyboard([BTN_PREV], per_row=1)
    )

@bot.on_button_callback("contact_call")
async def contact_call_handler(cb: aiomax.Callback):
    user_id = cb.user.user_id
    current = get_user_data(user_id)
    current["contact_method"] = "Звонок"
    set_user_data(user_id, current)
    set_user_state(user_id, STATE_PHONE)
    
    phone_number = "+79220392000"
    await cb.answer(
        text=(
            f"Отлично! Оставьте ваш номер телефона в формате **79999999999**, "
            f"чтобы мы могли вам перезвонить. Или звоните сами: {phone_number} 👇"
        ),
        keyboard=make_keyboard([BTN_PREV], per_row=1)
    )

# ============================================================
# Ввод телефона / Площади / Площадей по комнатам / GigaChat
# ============================================================

@bot.on_message()
async def handle_text(message: aiomax.Message):
    user_id = message.sender.user_id
    update_user_activity(user_id)
    state = get_user_state(user_id)
    text = message.content if message.content else None

    if not text:
        return

    # --- УМНЫЕ КОМАНДЫ (работают в любом состоянии) ---
    text_lower = text.lower()
    
    # 1. Возврат в меню (по тексту)
    if any(word in text_lower for word in ["верни", "меню", "назад в меню", "главное меню"]):
        clear_user(user_id)
        await message.reply(WELCOME_TEXT, keyboard=WELCOME_KB)
        return

    # 2. Начало расчета (по тексту)
    calc_keywords = ["рассчит", "стоимост", "сколько сто", "цена", "узнать стоим", "начать ремонт", "хочу ремонт", "сделать ремонт", "заказать ремонт", "мне нужен расчет"]
    if any(keyword in text_lower for keyword in calc_keywords):
        set_user_state(user_id, STATE_HOUSING)
        set_user_data(user_id, {"rooms_list": []})
        
        kb = make_keyboard([
            ("Новостройка", "housing_new"), ("Вторичка", "housing_secondary"),
            ("Дом", "housing_house"), ("Другое", "housing_other"), BTN_BACK
        ], per_row=2)
        await message.reply("Шаг 1. Где нужно сделать ремонт?", keyboard=kb)
        return

    # --- Ввод площади для конкретной комнаты ---
    if state == STATE_ROOM_AREA:
        area_match = re.search(r"\d+", text)
        if area_match:
            current = get_user_data(user_id)
            rooms_to_process = current.get("rooms_to_process", [])
            
            if rooms_to_process:
                current_room = rooms_to_process[0]
                areas = current.get("areas", {})
                areas[current_room] = area_match.group()
                current["areas"] = areas
                current["rooms_to_process"] = rooms_to_process[1:]
                set_user_data(user_id, current)
            
            if current["rooms_to_process"]:
                next_room = current["rooms_to_process"][0]
                kb = make_keyboard([BTN_UNKNOWN_AREA, BTN_BACK], per_row=1)
                await message.reply(f"Какая площадь у комнаты **{next_room}**? (в м²)", keyboard=kb)
            else:
                set_user_state(user_id, STATE_CEILING)
                kb = make_keyboard([
                    ("До 2.7 м (стандарт)", "ceiling_27"),
                    ("2.7 - 3.2 м", "ceiling_32"),
                    ("Выше 3.2 м", "ceiling_high"),
                    ("Не знаю", "ceiling_unknown"),
                    BTN_BACK
                ], per_row=2)
                await message.reply("Шаг 4. Какая высота потолков в помещении?", keyboard=kb)
        else:
            kb = make_keyboard([BTN_UNKNOWN_AREA, BTN_BACK], per_row=1)
            await message.reply("Пожалуйста, напишите число (например, 15) или выберите «Не знаю» 👇", keyboard=kb)
        return

    # --- Ввод телефона (после выбора способа связи) ---
    if state == STATE_PHONE:
        phone_clean = re.sub(r"\D", "", text)
        
        # 1. Если ввели 11 цифр (телефон)
        if len(phone_clean) == 11 and (phone_clean.startswith("7") or phone_clean.startswith("8")):
            if phone_clean.startswith("8"):
                phone_clean = "7" + phone_clean[1:]
            
            current = get_user_data(user_id)
            current["phone"] = phone_clean
            set_user_data(user_id, current)
            await finalize_lead(message, user_id)
            
        # 2. Если ввели ник (@...)
        elif text.startswith("@"):
            current = get_user_data(user_id)
            current["phone"] = text
            set_user_data(user_id, current)
            await finalize_lead(message, user_id)
            
        # 3. Если ввели имя (только буквы, без цифр)
        elif text.replace(" ", "").isalpha():
            current = get_user_data(user_id)
            current["phone"] = text
            set_user_data(user_id, current)
            await finalize_lead(message, user_id)
            
        else:
            # Это ни на что не похоже — просим заново
            await message.reply(
                "Не удалось распознать контакт. Пожалуйста, введите ваш номер телефона (например, **79999999999**) "
                "или ваше имя для связи.",
                keyboard=make_keyboard([BTN_PREV], per_row=1)
            )
        return

    # --- Свободный вопрос (GigaChat или Фото) ---
    if state is None:
        current = fsm_states.get(user_id, {})
        
        # Если пользователь еще не получал приветствие
        if not current.get("greeted"):
            current["greeted"] = True
            fsm_states[user_id] = current
            await message.reply(WELCOME_TEXT, keyboard=WELCOME_KB)
            return

        # Проверяем, не просит ли клиент фото
        photo_keywords = ["фото", "покажи", "пример", "работ", "портфолио", "как выглядит", "визуал"]
        text_lower = text.lower()
        
        if any(keyword in text_lower for keyword in photo_keywords):
            await message.reply("📸 Секунду, подберу для вас примеры наших работ...")
            
            folder_path = os.path.join("media", "portfolio")
            attachments = []
            if os.path.exists(folder_path):
                # Берем до 5 случайных фото из портфолио
                files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                if files:
                    random_files = random.sample(files, min(5, len(files)))
                    for filename in random_files:
                        try:
                            attachment = await bot.upload_image(os.path.join(folder_path, filename))
                            attachments.append(attachment)
                        except Exception as e:
                            print(f"Ошибка загрузки фото {filename}: {e}")
            
            if attachments:
                await message.reply(
                    "Вот несколько примеров наших объектов. Если хотите узнать стоимость ремонта — нажмите «Узнать стоимость» 👇",
                    attachments=attachments,
                    keyboard=make_keyboard([("✅ Узнать стоимость", "start_quiz"), BTN_BACK], per_row=1)
                )
            else:
                await message.reply("Фотографии временно недоступны. Пожалуйста, нажмите «Узнать стоимость», чтобы мы рассчитали ваш ремонт 👇")
            return

        # Если фото не просят — отвечаем через GigaChat
        try:
            answer = ask_gigachat_ultra(text)
            await message.reply(answer)
        except Exception as e:
            print(f"Ошибка GigaChat: {e}")
            await message.reply("Пожалуйста, нажмите /start, чтобы начать 👇")
        return

# ============================================================
# ФИНАЛИЗАЦИЯ
# ============================================================

async def finalize_lead(message: aiomax.Message, user_id):
    data = get_user_data(user_id)
    method = data.get("contact_method", "Не указан")
    
    areas_dict = data.get("areas", {})
    areas_str = ", ".join([f"{room}: {area}" for room, area in areas_dict.items()])
    if not areas_str:
        areas_str = "Не указаны"
        
    admin_text = (
        f"🔔 Новая заявка на ремонт!\n"
        f"Способ связи: {method}\n\n"
        f"📞 Телефон/Ник: {data.get('phone', '—')}\n"
        f"🏠 Тип жилья: {data.get('housing', '—')}\n"
        f"🚪 Комнаты: {data.get('rooms', '—')}\n"
        f"📐 Площади: {areas_str}\n"
        f"📏 Высота потолков: {data.get('ceiling', '—')}\n"
        f"🔨 Тип ремонта: {data.get('repair_type', '—')}\n"
        f"📅 Сроки: {data.get('timeline', '—')}\n"
        f"💰 Бюджет: {data.get('budget', '—')}"
    )
    
    try:
        await bot.send_message(admin_text, user_id=ADMIN_ID)
    except Exception as e:
        print(f"Ошибка отправки администратору: {e}")
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor_db.execute('''
        INSERT INTO leads (date, user_id, phone, housing, rooms, area, ceiling, repair_type, timeline, budget)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        current_time, user_id, data.get('phone', ''),
        data.get('housing', ''), data.get('rooms', ''),
        areas_str,
        data.get('ceiling', ''),
        data.get('repair_type', ''),
        data.get('timeline', ''), data.get('budget', '')
    ))
    conn.commit()
    
    kb = make_keyboard([BTN_BACK], per_row=1)
    await message.reply(
        text=(
            "Спасибо! Я уже получил ваши ответы.\n\n"
            "На основе этих данных я сделаю **предварительный** расчет. "
            "Однако **точная смета составляется только после выезда замерщика** на объект.\n\n"
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