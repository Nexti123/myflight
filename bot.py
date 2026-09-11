import os
import logging
import sys
import asyncio
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, add_subscription, get_all_subscriptions
from api import get_flight_info, get_weather, get_airport_board

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

app = Flask(__name__)

# Словарь для отслеживания состояний пользователей (например, ожидание кода аэропорта)
user_states = {}

@app.route("/")
def index():
    return "Flight Bot is active and running!"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_states.pop(message.chat.id, None)
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith("flight_"):
        flight_num = args[1].split("_")[1].upper()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(add_subscription(flight_num, message.from_user.id, message.from_user.id))
        loop.close()
        
        bot.send_message(
            message.chat.id,
            f"🔗 <b>Подписка оформлена!</b>\nВы подписались на обновления рейса <b>{flight_num}</b>."
        )
        show_flight_card(message.chat.id, flight_num)
        return

    send_main_menu(message.chat.id, message.from_user.first_name)

def send_main_menu(chat_id, name):
    user_states.pop(chat_id, None)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✈️ Найти рейс по номеру", callback_data="menu_enter_flight"))
    markup.add(InlineKeyboardButton("🔍 Ввести другой аэропорт (IATA)", callback_data="menu_enter_airport"))
    markup.add(
        InlineKeyboardButton("🛫 Шереметьево (SVO)", callback_data="board_SVO"),
        InlineKeyboardButton("🛫 Пулково (LED)", callback_data="board_LED")
    )
    markup.add(
        InlineKeyboardButton("🛫 Дубай (DXB)", callback_data="board_DXB"),
        InlineKeyboardButton("🛫 Анталья (AYT)", callback_data="board_AYT")
    )
    
    bot.send_message(
        chat_id,
        f"👋 Привет, <b>{name}</b>!\n\n"
        "✈️ <b>Живой тревел-ассистент готов к работе.</b>\n"
        "Выбери аэропорт для табло, нажми кнопку ввода своего аэропорта или просто отправь в чат **номер любого рейса** (например: <code>SU-1008</code>, <code>EK-131</code>).",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu_enter_flight")
def callback_enter_flight(call):
    user_states[call.message.chat.id] = "waiting_flight"
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id, 
        "✍️ <b>Введите номер рейса текстом</b>\n(например: <code>SU-1234</code>, <code>S7-2026</code>):"
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu_enter_airport")
def callback_enter_airport(call):
    user_states[call.message.chat.id] = "waiting_airport"
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id, 
        "✍️ <b>Введите 3-буквенный IATA код аэропорта</b>\n(например: <code>JFK</code>, <code>IST</code>, <code>VKO</code>, <code>AER</code>):"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("board_"))
def callback_board(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    airport_code = call.data.split("_")[1]
    show_airport_board(call.message.chat.id, airport_code)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_flight_"))
def callback_select_flight(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    flight_num = call.data.split("_")[2]
    show_flight_card(call.message.chat.id, flight_num)

@bot.callback_query_handler(func=lambda call: call.data == "menu_main")
def callback_main(call):
    send_main_menu(call.message.chat.id, call.from_user.first_name)

def show_airport_board(chat_id, airport_code):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    board = loop.run_until_complete(get_airport_board(airport_code))
    loop.close()

    markup = InlineKeyboardMarkup()
    for flight in board:
        btn_text = f"✈️ {flight['flight']} ➔ {flight['dest']} ({flight['time']})"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"select_flight_{flight['flight']}"))
    
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))

    bot.send_message(
        chat_id,
        f"📊 <b>Табло вылетов ({airport_code.upper()})</b>\nНажми на рейс для проверки статуса:",
        reply_markup=markup
    )

def show_flight_card(chat_id, flight_num):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    data = loop.run_until_complete(get_flight_info(flight_num))
    weather_arr = loop.run_until_complete(get_weather(data["arr_city_code"]))
    loop.close()

    bot_info = bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=flight_{data['flight']}"
    
    response_text = (
        f"✈️ <b>Рейс: {data['flight']}</b>\n"
        f"🏢 Авиакомпания: {data['airline']}\n"
        f"📌 Статус: <b>{data['status']}</b>\n\n"
        f"🛫 <b>Отправление:</b> {data['departure_airport']}\n"
        f"🕒 Время вылета: {data['departure_time']}\n\n"
        f"🛬 <b>Прибытие:</b> {data['arrival_airport']}\n"
        f"🕒 Расчетное время: {data['arrival_time']}\n"
        f"⏱ В пути: {data['duration']}\n\n"
        f"{weather_arr}\n\n"
        f"🚪 <b>Гейт:</b> {data['gate']} | Терминал: {data['terminal']}\n"
        f"🛩 Воздушное судно: {data['aircraft']}"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👨‍👩‍👧 Поделиться с родителями", url=f"https://t.me/share/url?url={share_link}&text=Следи за моим полетом в реальном времени!"))
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    
    bot.send_message(chat_id, response_text, reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_all_text(message):
    chat_id = message.chat.id
    text = message.text.strip().upper()
    
    # Проверяем, ожидал ли бот ввод аэропорта
    if user_states.get(chat_id) == "waiting_airport":
        user_states.pop(chat_id, None)
        if len(text) == 3:
            show_airport_board(chat_id, text)
        else:
            bot.send_message(chat_id, "❌ Неверный формат. Код аэропорта должен состоять из 3 букв (например: <code>JFK</code>). Попробуйте снова через меню.")
        return

    # В остальных случаях обрабатываем текст как номер рейса
    user_states.pop(chat_id, None)
    show_flight_card(chat_id, text)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    loop.close()

    port = int(os.getenv("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port)).start()
    
    print("🚀 Живой бот успешно запущен...")
    bot.infinity_polling(skip_pending=True)
