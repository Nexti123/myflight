import os
import logging
import sys
import asyncio
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, add_subscription
from api import get_flight_info, get_weather, get_airport_board

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

app = Flask(__name__)

@app.route("/")
def index():
    return "Flight Bot is active and running!"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith("flight_"):
        flight_num = args[1].split("_")[1].upper()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(add_subscription(flight_num, message.from_user.id, message.from_user.id))
        loop.close()
        
        bot.send_message(
            message.chat.id,
            f"🔗 Вы успешно подписались на отслеживание рейса <b>{flight_num}</b>!\n"
            "Я буду присылать вам все актуальные обновления."
        )
        show_flight_card(message.chat.id, flight_num)
        return

    send_main_menu(message.chat.id, message.from_user.first_name)

def send_main_menu(chat_id, name):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✈️ Ввести номер рейса", callback_data="menu_enter_flight"))
    markup.add(InlineKeyboardButton("📊 Табло аэропорта (SVO)", callback_data="menu_board"))
    
    bot.send_message(
        chat_id,
        f"Привет, <b>{name}</b>! ✈️\n"
        "Я твой личный тревел-ассистент. Выбери действие ниже или просто отправь мне номер рейса:",
        reply_markup=markup
    )

# Обработка нажатий на инлайн-кнопки
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    bot.answer_callback_query(call.id) # Снимаем анимацию загрузки с кнопки
    
    if call.data == "menu_enter_flight":
        bot.send_message(call.message.chat.id, "✍️ Отправь мне номер рейса (например: <code>SU-1234</code>):")
    
    elif call.data == "menu_board":
        show_airport_board(call.message.chat.id)
        
    elif call.data.startswith("select_flight_"):
        flight_num = call.data.split("_")[2]
        show_flight_card(call.message.chat.id, flight_num)

def show_airport_board(chat_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    board = loop.run_until_complete(get_airport_board("SVO"))
    loop.close()

    markup = InlineKeyboardMarkup()
    for flight in board:
        btn_text = f"{flight['flight']} | {flight['dest']} | {flight['time']}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"select_flight_{flight['flight']}"))
    
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))

    bot.send_message(
        chat_id,
        "📊 <b>Табло вылетов (Шереметьево, SVO):</b>\nНажми на рейс, чтобы посмотреть детальную информацию:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu_main")
def back_to_main(call):
    bot.answer_callback_query(call.id)
    send_main_menu(call.message.chat.id, call.from_user.first_name)

def show_flight_card(chat_id, flight_num):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    data = loop.run_until_complete(get_flight_info(flight_num))
    weather_arr = loop.run_until_complete(get_weather(data["arr_city_code"]))
    loop.close()

    bot_info = bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=flight_{data['flight']}"
    
    response_html = (
        f"✈️ <b>Информация о рейсе: {data['flight']}</b>\n"
        f"🏢 Авиакомпания: {data['airline']}\n"
        f"📊 Статус: {data['status']}\n\n"
        
        f"🛫 <b>Отправление:</b> {data['departure_airport']}\n"
        f"🕒 Время вылета: {data['departure_time']}\n\n"
        
        f"🛬 <b>Прибытие:</b> {data['arrival_airport']}\n"
