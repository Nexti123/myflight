import os
import logging
import sys
import asyncio
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, add_subscription, remove_subscription, check_subscription
from api import get_flight_info, get_weather, get_airport_board

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)
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
        
        bot.send_message(message.chat.id, f"🔗 <b>Подписка оформлена!</b> Вы подписались на рейс <b>{flight_num}</b>.")
        show_flight_card(message.chat.id, message.from_user.id, flight_num)
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
        "Выберите аэропорт для просмотра полного расписания на день, введите код или отправьте в чат **номер любого рейса**.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu_enter_flight")
def callback_enter_flight(call):
    user_states[call.message.chat.id] = "waiting_flight"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "✍️ <b>Введите номер рейса текстом</b>\n(например: <code>SU-1234</code>, <code>S7-2514</code>):")

@bot.callback_query_handler(func=lambda call: call.data == "menu_enter_airport")
def callback_enter_airport(call):
    user_states[call.message.chat.id] = "waiting_airport"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "✍️ <b>Введите 3-буквенный IATA код аэропорта</b>\n(например: <code>JFK</code>, <code>IST</code>, <code>VKO</code>):")

@bot.callback_query_handler(func=lambda call: call.data.startswith("board_"))
def callback_board(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    airport_code = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    show_airport_board(call.message.chat.id, airport_code, page)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_flight_"))
def callback_select_flight(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    flight_num = call.data.split("_")[2]
    show_flight_card(call.message.chat.id, call.from_user.id, flight_num)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_sub_"))
def callback_toggle_sub(call):
    flight_num = call.data.split("_")[2]
    user_id = call.from_user.id
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    is_subbed = loop.run_until_complete(check_subscription(flight_num, user_id))
    
    if is_subbed:
        loop.run_until_complete(remove_subscription(flight_num, user_id))
        bot.answer_callback_query(call.id, "🔕 Уведомления отключены")
    else:
        loop.run_until_complete(add_subscription(flight_num, user_id, user_id))
        bot.answer_callback_query(call.id, "🔔 Уведомления включены!")
    loop.close()
    
    show_flight_card(call.message.chat.id, user_id, flight_num, edit_message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "menu_main")
def callback_main(call):
    bot.answer_callback_query(call.id)
    send_main_menu(call.message.chat.id, call.from_user.first_name)

def show_airport_board(chat_id, airport_code, page=0):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    board = loop.run_until_complete(get_airport_board(airport_code))
    loop.close()

    if not board:
        bot.send_message(chat_id, f"❌ Не удалось получить расписание для аэропорта <b>{airport_code}</b>.")
        return

    # Разбиваем по 6 рейсов на страницу, чтобы можно было смотреть расписание на весь день по страницам
    per_page = 6
    total_pages = (len(board) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    
    chunk = board[page * per_page : (page + 1) * per_page]

    markup = InlineKeyboardMarkup()
    for flight in chunk:
        btn_text = f"✈️ {flight['flight']} ➔ {flight['dest']} ({flight['time']})"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"select_flight_{flight['flight']}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"board_{airport_code}_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"board_{airport_code}_{page + 1}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
        
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))

    text = f"📊 <b>Расписание рейсов на весь день ({airport_code.upper()})</b>\nСтраница {page + 1} из {total_pages}\nВыберите рейс для подробностей:"
    bot.send_message(chat_id, text, reply_markup=markup)

def show_flight_card(chat_id, user_id, flight_num, edit_message_id=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    data = loop.run_until_complete(get_flight_info(flight_num))
    
    if not data:
        loop.close()
        err_text = (
            f"❌ <b>Рейс {flight_num} не найден в активной мировой базе данных.</b>\n\n"
            "Возможные причины:\n"
            "• Рейс завершен или отменен;\n"
            "• Неправильно указан номер или код авиакомпании.\n\n"
            "Проверьте номер и попробуйте ввести его снова."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
        if edit_message_id:
            bot.edit_message_text(err_text, chat_id, edit_message_id, reply_markup=markup)
        else:
            bot.send_message(chat_id, err_text, reply_markup=markup)
        return

    weather_arr = loop.run_until_complete(get_weather(data["arr_query_for_weather"]))
    is_subbed = loop.run_until_complete(check_subscription(flight_num, user_id))
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
    sub_btn_text = "🔕 Выключить уведомления" if is_subbed else "🔔 Включить уведомления"
    markup.add(InlineKeyboardButton(sub_btn_text, callback_data=f"toggle_sub_{data['flight']}"))
    markup.add(InlineKeyboardButton("👨‍👩‍👧 Поделиться с близкими", url=f"https://t.me/share/url?url={share_link}&text=Следи за моим полетом в реальном времени!"))
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    
    if edit_message_id:
        bot.edit_message_text(response_text, chat_id, edit_message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, response_text, reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_all_text(message):
    chat_id = message.chat.id
    text = message.text.strip().upper()
    
    if user_states.get(chat_id) == "waiting_airport":
        user_states.pop(chat_id, None)
        if len(text) == 3:
            show_airport_board(chat_id, text)
        else:
            bot.send_message(chat_id, "❌ Неверный формат. Код аэропорта должен состоять из 3 букв (например: <code>JFK</code>).")
        return

    user_states.pop(chat_id, None)
    show_flight_card(chat_id, message.from_user.id, text)

if __name__ == "__main__":
    logging.info("🔄 Инициализация базы данных...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    loop.close()

    port = int(os.getenv("PORT", 10000))
    logging.info(f"🌐 Запуск веб-сервера Flask на порту {port}...")
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()
    
    logging.info("🚀 Бот запущен и слушает обновления от Telegram...")
    bot.infinity_polling(skip_pending=True)
