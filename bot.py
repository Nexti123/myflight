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
from api import get_flight_info, get_weather, get_airport_board, get_airport_details

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Память для интерактивных фич (чек-листы, заметки, трансферы)
user_states = {}
user_checklists = {}
user_notes = {}
user_transfers = {}

@app.route("/")
def index():
    return "Flight Bot is active and running!"

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
        InlineKeyboardButton("🛫 Пулково (LED)", callback_data="board_LED")
    )
    markup.add(
        InlineKeyboardButton("🛫 Дубай (DXB)", callback_data="board_DXB"),
        InlineKeyboardButton("🛫 Анталья (AYT)", callback_data="board_AYT")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_states.pop(message.chat.id, None)
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith("flight_"):
        flight_num = args[1].split("_")[1].upper()
        run_async(add_subscription(flight_num, message.from_user.id, message.from_user.id))
        bot.send_message(message.chat.id, f"🔗 <b>Подписка оформлена!</b> Вы подписались на рейс <b>{flight_num}</b>.")
        show_flight_card(message.chat.id, message.from_user.id, flight_num)
        return

    bot.send_message(
        message.chat.id,
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        "✈️ <b>Твой персональный тревел-ассистент готов к работе.</b>\n"
        "Выбери нужный раздел в меню ниже:",
        reply_markup=get_main_menu_markup()
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu_main")
def callback_main(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"👋 Привет, <b>{call.from_user.first_name}</b>!\n\n"
        "✈️ <b>Твой персональный тревел-ассистент готов к работе.</b>\n"
        "Выбери нужный раздел в меню ниже:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=get_main_menu_markup()
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

@bot.callback_query_handler(func=lambda call: call.data == "menu_my_flights")
def callback_my_flights(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    try:
        conn = sqlite3.connect("flights.db")
        cursor = conn.cursor()
        cursor.execute("SELECT flight_number FROM subscriptions WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        rows = []

    markup = InlineKeyboardMarkup()
    if rows:
        for row in rows:
            f_num = row[0]
            markup.add(InlineKeyboardButton(f"✈️ Рейс {f_num}", callback_data=f"select_flight_{f_num}"))
        text = "🧳 <b>Личный кабинет: Ваши активные полеты</b>\nВыберите рейс для просмотра детальной информации:"
    else:
        text = "🧳 <b>Личный кабинет пуст.</b>\nУ вас пока нет активных подписок на рейсы. Найдите рейс через поиск или табло!"

    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

# --- ЧЕК-ЛИСТ БАГАЖА ---
@bot.callback_query_handler(func=lambda call: call.data == "menu_checklist")
def callback_checklist(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    if user_id not in user_checklists:
        user_checklists[user_id] = {
            "Паспорт и билеты 🛂": False,
            "Деньги и карты 💳": False,
            "Зарядки и гаджеты 🔋": False,
            "Аптечка и лекарства 💊": False,
            "Средства гигиены 🧴": False,
            "Сменный комплект одежды 👕": False
        }
    show_checklist_menu(call.message.chat.id, user_id, edit_id=call.message.message_id)

def show_checklist_menu(chat_id, user_id, edit_id=None):
    items = user_checklists[user_id]
    markup = InlineKeyboardMarkup()
    for item, checked in items.items():
        status = "✅" if checked else "⬜️"
        markup.add(InlineKeyboardButton(f"{status} {item}", callback_data=f"check_toggle_{item}"))
    markup.add(InlineKeyboardButton("🔄 Сбросить все", callback_data="check_reset"))
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    
    text = "🎒 <b>Интерактивный чек-лист сбора багажа</b>\nНажимайте на пункты, чтобы отмечать собранные вещи:"
    if edit_id:
        bot.edit_message_text(text, chat_id, edit_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
def callback_checklist_action(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    if user_id not in user_checklists:
        return
    
    if call.data == "check_reset":
        for k in user_checklists[user_id]:
            user_checklists[user_id][k] = False
    else:
        item = call.data.replace("check_toggle_", "")
        if item in user_checklists[user_id]:
            user_checklists[user_id][item] = not user_checklists[user_id][item]
            
    show_checklist_menu(call.message.chat.id, user_id, edit_id=call.message.message_id)

# --- МЕНЕДЖЕР ЗАМЕТОК И ДОКУМЕНТОВ ---
@bot.callback_query_handler(func=lambda call: call.data == "menu_notes")
def callback_notes(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    note = user_notes.get(user_id, "<i>У вас пока нет сохраненных заметок.</i>")
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✏️ Изменить заметку", callback_data="notes_edit"))
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    
    text = f"📂 <b>Ваши сохраненные заметки и брони:</b>\n\n{note}"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "notes_edit")
def callback_notes_edit(call):
    bot.answer_callback_query(call.id)
    user_states[call.message.chat.id] = "waiting_note"
    bot.send_message(call.message.chat.id, "✍️ <b>Отправьте текст заметок следующим сообщением</b>\n(например: номера брони отеля, пин-коды или важную информацию):")

# --- КАЛЕНДАРЬ И ТРАНСФЕР-ТАЙМЕР ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("export_ics_"))
def callback_export_ics(call):
    bot.answer_callback_query(call.id, "📅 Событие готово для добавления в календарь!")
    flight_num = call.data.split("_")[2]
    bot.send_message(
        call.message.chat.id,
        f"📅 <b>Экспорт рейса {flight_num} в календарь</b>\n\n"
        f"Вы можете вручную добавить полет в свой календарь (Apple / Google) на время вылета.\n"
        f"<i>Совет: Рекомендуется поставить напоминание за 4 часа до отправления.</i>"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("transfer_"))
def callback_transfer(call):
    bot.answer_callback_query(call.id)
    flight_num = call.data.split("_")[2]
    user_states[call.message.chat.id] = f"waiting_address_{flight_num}"
    bot.send_message(
        call.message.chat.id,
        f"⏱ <b>Умный Трансфер-таймер для рейса {flight_num}</b>\n\n"
        f"Напишите ваш текущий адрес отправления (например: <i>ул. Тверская, 15</i> или <i>центр города</i>):"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("board_"))
def callback_board(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    show_airport_board(call.message.chat.id, parts[1], int(parts[2]) if len(parts) > 2 else 0, edit_message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_flight_"))
def callback_select_flight(call):
    user_states.pop(call.message.chat.id, None)
    bot.answer_callback_query(call.id)
    show_flight_card(call.message.chat.id, call.from_user.id, call.data.split("_")[2], edit_message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_sub_"))
def callback_toggle_sub(call):
    flight_num = call.data.split("_")[2]
    user_id = call.from_user.id
    if run_async(check_subscription(flight_num, user_id)):
        run_async(remove_subscription(flight_num, user_id))
        bot.answer_callback_query(call.id, "🔕 Уведомления отключены")
    else:
        run_async(add_subscription(flight_num, user_id, user_id))
        bot.answer_callback_query(call.id, "🔔 Уведомления включены!")
    show_flight_card(call.message.chat.id, user_id, flight_num, edit_message_id=call.message.message_id)

def show_airport_board(chat_id, airport_code, page=0, edit_message_id=None):
    board = run_async(get_airport_board(airport_code))
    airport_info = get_airport_details(airport_code)

    if not board:
        msg = f"❌ Не удалось получить расписание для аэропорта <b>{airport_code}</b>."
        if edit_message_id: bot.edit_message_text(msg, chat_id, edit_message_id)
        else: bot.send_message(chat_id, msg)
        return

    per_page = 6
    total_pages = (len(board) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    chunk = board[page * per_page : (page + 1) * per_page]

    markup = InlineKeyboardMarkup()
    for flight in chunk:
        markup.add(InlineKeyboardButton(f"{flight['time']} | {flight['flight']} ➔ {flight['dest']} ({flight['status']})", callback_data=f"select_flight_{flight['flight']}"))
    
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"board_{airport_code}_{page - 1}"))
    if page < total_pages - 1: nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"board_{airport_code}_{page + 1}"))
    if nav_buttons: markup.row(*nav_buttons)
    
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))

    text = f"{airport_info}\n\n📊 <b>Онлайн-табло на весь день</b> (Страница {page + 1} из {total_pages})"
    if edit_message_id: bot.edit_message_text(text, chat_id, edit_message_id, reply_markup=markup)
    else: bot.send_message(chat_id, text, reply_markup=markup)

def show_flight_card(chat_id, user_id, flight_num, edit_message_id=None):
    data = run_async(get_flight_info(flight_num))
    
    if not data:
        err_text = f"❌ <b>Рейс {flight_num} не найден в активной базе данных.</b>"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
        if edit_message_id: bot.edit_message_text(err_text, chat_id, edit_message_id, reply_markup=markup)
        else: bot.send_message(chat_id, err_text, reply_markup=markup)
        return

    weather_arr = run_async(get_weather(data["arr_query_for_weather"]))
    is_subbed = run_async(check_subscription(flight_num, user_id))
    bot_info = bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=flight_{data['flight']}"
    
    response_text = (
        f"✈️ <b>Рейс: {data['flight']}</b>\n"
        f"🏢 Авиакомпания: {data['airline']}\n"
        f"📌 Статус: <b>{data['status']}</b>\n\n"
        f"🛫 <b>Отправление:</b> {data['departure_airport']}\n"
        f"🕒 Вылет: {data['departure_time']} | Гейт: <b>{data['dep_gate']}</b> (Терминал {data['dep_terminal']})\n\n"
        f"🛬 <b>Прибытие:</b> {data['arrival_airport']}\n"
        f"🕒 Прибытие: {data['arrival_time']} | Гейт: <b>{data['arr_gate']}</b> (Терминал {data['arr_terminal']})\n\n"
        f"⏰ {data['tz_diff']}\n"
        f"{weather_arr}\n\n"
        f"🛩 Воздушное судно: {data['aircraft']}"
    )
    
    markup = InlineKeyboardMarkup()
    sub_btn_text = "🔕 Выключить уведомления" if is_subbed else "🔔 Включить уведомления"
    markup.add(InlineKeyboardButton(sub_btn_text, callback_data=f"toggle_sub_{data['flight']}"))
    
    if data["fr24_link"]:
        markup.add(InlineKeyboardButton("🗺 Посмотреть на карте (Flightradar24)", url=data["fr24_link"]))
    
    markup.add(
        InlineKeyboardButton("⏱ Умный трансфер", callback_data=f"transfer_{data['flight']}"),
        InlineKeyboardButton("📅 В календарь", callback_data=f"export_ics_{data['flight']}")
    )
    markup.add(InlineKeyboardButton("👨‍👩‍👧 Ссылка для встречающих", url=f"https://t.me/share/url?url={share_link}&text=Следи за моим полетом в реальном времени!"))
    markup.add(InlineKeyboardButton("◀️ Главное меню", callback_data="menu_main"))
    
    if edit_message_id: bot.edit_message_text(response_text, chat_id, edit_message_id, reply_markup=markup)
    else: bot.send_message(chat_id, response_text, reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_all_text(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_states.get(chat_id)
    
    if state == "waiting_airport":
        user_states.pop(chat_id, None)
        if len(text) == 3: show_airport_board(chat_id, text.upper())
        else: bot.send_message(chat_id, "❌ Код аэропорта должен состоять из 3 букв (например: <code>JFK</code>).")
        return

    if state == "waiting_note":
        user_states.pop(chat_id, None)
        user_notes[message.from_user.id] = text
        bot.send_message(message.chat.id, "✅ <b>Заметки успешно сохранены!</b> Вы можете посмотреть их в главном меню в разделе «Заметки и брони».", reply_markup=get_main_menu_markup())
        return

    if state and state.startswith("waiting_address_"):
        flight_num = state.split("_")[2]
        user_states.pop(chat_id, None)
        bot.send_message(
            chat_id,
            f"🕒 <b>Расчет трансфера для рейса {flight_num}:</b>\n\n"
            f"📍 Адрес отправления: <b>{text}</b>\n"
            f"🚗 Расчетное время в дороге до аэропорта: ~<b>1 час 15 минут</b>\n"
            f"⏱ Рекомендуемый запас на досмотр и регистрацию: <b>2.5 часа</b>\n\n"
            f"🚨 <b>Итог: Рекомендуем выехать из дома примерно за 3 часа 45 минут до вылета!</b>",
            reply_markup=get_main_menu_markup()
        )
        return

    user_states.pop(chat_id, None)
    show_flight_card(chat_id, message.from_user.id, text.upper())

if __name__ == "__main__":
    logging.info("🔄 Инициализация базы данных...")
    run_async(init_db())

    port = int(os.getenv("PORT", 10000))
    logging.info(f"🌐 Запуск веб-сервера Flask на порту {port}...")
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()
    
    logging.info("🚀 Бот запущен и слушает обновления от Telegram...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            logging.error(f"❌ Ошибка в работе бота: {e}. Переподключение через 5 секунд...")
            import time
            time.sleep(5)
