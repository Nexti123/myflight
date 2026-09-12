# -*- coding: utf-8 -*-
import os
import logging
import sys
import asyncio
import threading
import sqlite3
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, add_subscription, remove_subscription, check_subscription
from api import get_flight_info, get_weather, get_airport_board, get_airport_details, calculate_real_transfer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

user_states = {}
user_checklists = {}
user_notes = {}

@app.route("/")
def index():
    return "Flight Bot is active!"

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def get_main_menu_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✈️ Найти рейс по номеру", callback_data="menu_enter_flight"))
    markup.add(InlineKeyboardButton("🧳 Мои полеты (Кабинет)", callback_data="menu_my_flights"))
    markup.add(
        InlineKeyboardButton("🎒 Чек-лист багажа", callback_data="menu_checklist"),
        InlineKeyboardButton("📂 Заметки и брони", callback_data="menu_notes")
    )
    markup.add(InlineKeyboardButton("🔍 Онлайн-табло аэропорта", callback_data="menu_enter_airport"))
    markup.add(
        InlineKeyboardButton("🛫 Шереметьево (SVO)", callback_data="board_SVO"),
        InlineKeyboardButton("🛫 Домодедово (DME)", callback_data="board_DME")
    )
    markup.add(
        InlineKeyboardButton("🛫 Толмачево (OVB)", callback_data="board_OVB"),
        InlineKeyboardButton("🛫 Пулково (LED)", callback_data="board_LED")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_states.pop(message.chat.id, None)
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("flight_"):
        flight_num = args[1].split("_")[1].upper()
        run_async(add_subscription(flight_num, message.from_user.id, message.from_user.id))
        bot.send_message(message.chat.id, f"🔗 <b>Подписка оформлена!</b> Рейс <b>{flight_num}</b> добавлен в кабинет.")
        show_flight_card(message.chat.id, message.from_user.id, flight_num)
        return

    bot.send_message(
        message.chat.id,
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n✈️ <b>Твой тревел-ассистент готов к работе.</b> Выбери пункт меню:",
        reply_markup=get_main_menu_markup()
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu_main")
def callback_main(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"👋 Привет, <b>{call.from_user.first_name}</b>!\n\n✈️ <b>Твой тревел-ассистент готов к работе.</b> Выбери пункт меню:",
        call.message.chat.id, call.message.message_id, reply_markup=get_main_menu_markup()
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu_enter_flight")
def callback_enter_flight(call):
    user_states[call.message.chat.id] = "waiting_flight"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "✍️ <b>Введите номер рейса текстом</b> (например: <code>SU-1430</code>, <code>S7-2514</code>):")

@bot.callback_query_handler(func=lambda call: call.data == "menu_enter_airport")
def callback_enter_airport(call):
    user_states[call.message.chat.id] = "waiting_airport"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "✍️ <b>Введите 3-буквенный IATA код аэропорта</b> (например: <code>SVO</code>, <code>OVB</code>, <code>DME</code>):")

@bot.callback_query_handler(func=lambda call: call.data == "menu_my_flights")
def callback_my_flights(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    rows = []
    try:
        conn = sqlite3.connect("flights.db")
        cursor = conn.cursor()
        cursor.execute("SELECT flight_number FROM subscriptions WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        pass

    markup = InlineKeyboardMarkup()
    if rows:
        for row in rows:
            f_num = row[0]
            markup.add(InlineKeyboardButton(f"✈️ Рейс {f_num}", callback_data=f"select_flight_{f_num}"))
        text = "🧳 <b>Личный кабинет: Ваши подписки</b>\nНажмите на рейс для просмотра актуальных данных:"
    else:
        text = "🧳 <b>Личный кабинет пуст.</b>\nУ вас нет сохраненных рейсов."

    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "menu_checklist")
def callback_checklist(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    if user_id not in user_checklists:
        user_checklists[user_id] = {"Паспорт и билеты 🛂": False, "Деньги и карты 💳": False, "Зарядки 🔋": False, "Аптечка 💊": False, "Одежда 👕": False}
    show_checklist(call.message.chat.id, user_id, call.message.message_id)

def show_checklist(chat_id, user_id, msg_id):
    markup = InlineKeyboardMarkup()
    for item, checked in user_checklists[user_id].items():
        markup.add(InlineKeyboardButton(f"{'✅' if checked else '⬜️'} {item}", callback_data=f"chk_{item}"))
    markup.add(InlineKeyboardButton("🔄 Сбросить", callback_data="chk_reset"), InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    bot.edit_message_text("🎒 <b>Чек-лист багажа:</b>", chat_id, msg_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chk_"))
def callback_chk_action(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    if call.data == "chk_reset":
        for k in user_checklists[user_id]: user_checklists[user_id][k] = False
    else:
        item = call.data.replace("chk_", "")
        if item in user_checklists[user_id]: user_checklists[user_id][item] = not user_checklists[user_id][item]
    show_checklist(call.message.chat.id, user_id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "menu_notes")
def callback_notes(call):
    bot.answer_callback_query(call.id)
    note = user_notes.get(call.from_user.id, "<i>Нет сохраненных заметок.</i>")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✏️ Изменить заметку", callback_data="notes_edit"), InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    bot.edit_message_text(f"📂 <b>Заметки и брони:</b>\n\n{note}", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "notes_edit")
def callback_notes_edit(call):
    bot.answer_callback_query(call.id)
    user_states[call.message.chat.id] = "waiting_note"
    bot.send_message(call.message.chat.id, "✍️ <b>Отправьте текст заметок следующим сообщением:</b>")

@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_"))
def callback_transfer(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    flight_num = parts[1]
    dep_iata = parts[2] if len(parts) > 2 else "OVB"
    
    user_states[call.message.chat.id] = f"waiting_transfer_{flight_num}_{dep_iata}"
    bot.send_message(call.message.chat.id, f"⏱ <b>Умный Трансфер для рейса {flight_num}</b>\nВведите ваш адрес отправления (например: <i>Красный проспект 100</i> или <i>ул. Тверская 12</i>):")

@bot.callback_query_handler(func=lambda call: call.data.startswith("export_ics_"))
def callback_ics(call):
    bot.answer_callback_query(call.id, "📅 Готово!")
    bot.send_message(call.message.chat.id, f"📅 <b>Календарь:</b> Рейс {call.data.split('_')[2]} сохранен. Поставьте будильник за 4 часа до вылета.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("board_"))
def callback_board(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    code = call.data.split("_")[1]
    show_airport_board(call.message.chat.id, code, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_flight_"))
def callback_select_flight(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    show_flight_card(call.message.chat.id, call.from_user.id, call.data.split("_")[2], call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_sub_"))
def callback_toggle_sub(call):
    flight_num = call.data.split("_")[2]
    user_id = call.from_user.id
    if run_async(check_subscription(flight_num, user_id)):
        run_async(remove_subscription(flight_num, user_id))
        bot.answer_callback_query(call.id, "🔕 Уведомления выключены")
    else:
        run_async(add_subscription(flight_num, user_id, user_id))
        bot.answer_callback_query(call.id, "🔔 Уведомления включены!")
    show_flight_card(call.message.chat.id, user_id, flight_num, call.message.message_id)

def show_airport_board(chat_id, code, msg_id=None):
    board = run_async(get_airport_board(code))
    info = get_airport_details(code)
    
    if not board:
        text = f"{info}\n\n⚠️ <b>Онлайн-табло временно недоступно.</b>\nПроверьте переменную <code>YANDEX_RASP_API_KEY</code> на Render."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
        if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)
        return

    lines = [f"{info}\n\n📊 <b>Онлайн-табло вылетов:</b>\n"]
    for f in board[:30]:
        lines.append(f"⏱ <code>{f['time']}</code> | <b>{f['flight']}</b> ➔ {f['dest']}")

    text_content = "\n".join(lines)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))

    if msg_id:
        try:
            bot.edit_message_text(text_content, chat_id, msg_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text_content, reply_markup=markup)
    else:
        bot.send_message(chat_id, text_content, reply_markup=markup)

def show_flight_card(chat_id, user_id, flight_num, msg_id=None):
    data = run_async(get_flight_info(flight_num))
    weather = run_async(get_weather(data.get("arr_query_for_weather", "Москва")))
    is_sub = run_async(check_subscription(flight_num, user_id))
    bot_info = bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=flight_{data['flight']}"
    
    text = (
        f"✈️ <b>Рейс: {data['flight']}</b>\n"
        f"🏢 Авиакомпания: {data['airline']}\n"
        f"📌 Статус: <b>{data['status']}</b>\n\n"
        f"🛫 <b>Отправление:</b> {data['departure_airport']}\n"
        f"🕒 Время: {data['departure_time']} | Гейт: <b>{data['dep_gate']}</b> (Терминал: {data['dep_terminal']})\n\n"
        f"🛬 <b>Прибытие:</b> {data['arrival_airport']}\n"
        f"🕒 Время: {data['arrival_time']} | Гейт: <b>{data['arr_gate']}</b> (Терминал: {data['arr_terminal']})\n\n"
        f"{weather}\n\n"
        f"🛩 Судно: {data['aircraft']}"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔕 Выключить уведомления" if is_sub else "🔔 Включить уведомления", callback_data=f"toggle_sub_{data['flight']}"))
    if data["fr24_link"]:
        markup.add(InlineKeyboardButton("🗺 Посмотреть на Flightradar24", url=data["fr24_link"]))
    markup.add(
        InlineKeyboardButton("⏱ Трансфер", callback_data=f"transfer_{data['flight']}_{data['departure_iata']}"),
        InlineKeyboardButton("📅 В календарь", callback_data=f"export_ics_{data['flight']}")
    )
    markup.add(InlineKeyboardButton("👨‍👩‍👧 Ссылка для встречающих", url=f"https://t.me/share/url?url={share_link}&text=Следи за моим полетом!"))
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
    else: bot.send_message(chat_id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_all_text(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_states.get(chat_id)
    
    if state == "waiting_flight":
        user_states.pop(chat_id, None)
        show_flight_card(chat_id, message.from_user.id, text.upper())
        return

    if state == "waiting_airport":
        user_states.pop(chat_id, None)
        show_airport_board(chat_id, text.upper()[:3])
        return

    if state == "waiting_note":
        user_states.pop(chat_id, None)
        user_notes[message.from_user.id] = text
        bot.send_message(chat_id, "✅ <b>Заметки сохранены!</b>", reply_markup=get_main_menu_markup())
        return

    if state and state.startswith("waiting_transfer_"):
        parts = state.split("_")
        flight_num = parts[2]
        dep_iata = parts[3]
        user_states.pop(chat_id, None)
        
        bot.send_message(chat_id, "🛰 Прокладываем автомобильный маршрут...")
        transfer_data = run_async(calculate_real_transfer(text, dep_iata))
        
        if not transfer_data:
            bot.send_message(
                chat_id, 
                "❌ Не удалось проложить маршрут по данному адресу. Укажите город и улицу точнее (например: <i>Новосибирск, Красный проспект 100</i> или <i>Москва, Тверская 12</i>).",
                reply_markup=get_main_menu_markup()
            )
            return
            
        dist = transfer_data["distance"]
        t_str = transfer_data["time_str"]
        total_mins = transfer_data["total_minutes"]
        
        airport_buffer = 150  # 2.5 часа на сборы и досмотр
        total_needed_mins = total_mins + airport_buffer
        
        rec_hours = total_needed_mins // 60
        rec_mins = total_needed_mins % 60
        
        bot.send_message(
            chat_id,
            f"📍 <b>Расчет трансфера для рейса {flight_num}:</b>\n\n"
            f"🛣 Дистанция до аэропорта: <b>{dist} км</b>\n"
            f"🚗 Время в дороге на авто: <b>{t_str}</b>\n"
            f"⏱ Запас на регистрацию и досмотр: <b>2 ч. 30 мин.</b>\n\n"
            f"🚨 <b>Выезжайте за {rec_hours} ч. {rec_mins} мин. до вылета!</b>",
            reply_markup=get_main_menu_markup()
        )
        return

    user_states.pop(chat_id, None)
    show_flight_card(chat_id, message.from_user.id, text.upper())

if __name__ == "__main__":
    run_async(init_db())
    port = int(os.getenv("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            logging.error(f"Ошибка: {e}")
            import time
            time.sleep(5)
