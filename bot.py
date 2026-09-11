import os
import logging
import sys
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, add_subscription
from api import get_flight_info, get_weather

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Flask-сервер для того, чтобы Render не усыплял бота
app = Flask(__name__)

@app.route("/")
def index():
    return "Flight Bot is active and running!"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    args = message.text.split()
    
    # Если перешли по ссылке вида t.me/bot?start=flight_SU1234
    if len(args) > 1 and args[1].startswith("flight_"):
        flight_num = args[1].split("_")[1].upper()
        # Регистрируем подписчика
        import asyncio
        asyncio.run(add_subscription(flight_num, message.from_user.id, message.from_user.id))
        
        bot.send_message(
            message.chat.id,
            f"🔗 Вы успешно подписались на отслеживание рейса <b>{flight_num}</b>!\n"
            "Я буду присылать вам все актуальные обновления."
        )
        show_flight_card(message.chat.id, flight_num)
        return

    # Обычное стартовое меню
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✈️ Ввести номер рейса", callback_data="enter_flight"))
    markup.add(InlineKeyboardButton("📊 Табло аэропорта", callback_data="airport_board"))
    
    bot.send_message(
        message.chat.id,
        f"Привет, <b>{message.from_user.first_name}</b>! ✈️\n"
        "Я твой личный тревел-ассистент. Помогу отследить полеты, узнать погоду и поделюсь информацией с близкими.",
        reply_markup=markup
    )

def show_flight_card(chat_id, flight_num):
    import asyncio
    # Получаем данные через асинхронные функции в синхронном потоке
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
        f"🕒 Расчетное время: {data['arrival_time']}\n"
        f"⏳ Время в пути: {data['duration']}\n"
        f"{weather_arr}\n\n"
        
        f"🚪 <b>Гейт:</b> {data['gate']} (Терминал {data['terminal']})\n"
        f"🛩 Самолёт: {data['aircraft']}"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👨‍👩‍👧 Поделиться с родителями", url=f"https://t.me/share/url?url={share_link}&text=Следи за моим полетом в реальном времени!"))
    
    bot.send_message(chat_id, response_html, reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_all_text(message):
    flight_num = message.text.strip().upper()
    show_flight_card(message.chat.id, flight_num)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    import threading
    
    # Инициализируем БД при старте
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    loop.close()

    # Запускаем Flask в отдельном потоке (для Render)
    port = int(os.getenv("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port)).start()
    
    # Запускаем бота
    print("Бот запущен...")
    bot.infinity_polling()
