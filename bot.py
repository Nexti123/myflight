import asyncio
import logging
import datetime
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from FlightRadarAPI import FlightRadar24API
import requests
from threading import Thread
from flask import Flask

# Инициализация логирования
logging.basicConfig(level=logging.INFO)

# Безопасное чтение токена из переменных окружения Render
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    logging.error("❌ Ошибка: Не найден токен BOT_TOKEN в переменных окружения!")

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

fr_api = FlightRadar24API()

# Хранилище данных в памяти
user_data_storage = {}

def get_user_storage(user_id: int):
    if user_id not in user_data_storage:
        user_data_storage[user_id] = {
            "checklist": {"Паспорт": False, "Билеты": False, "Зарядка": False, "Аптечка": False},
            "notes": "Пока нет записей.",
            "tracked_flight": None
        }
    return user_data_storage[user_id]

# Главное меню
def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✈️ Найти рейс (FR24)", callback_data="menu_flight")],
        [InlineKeyboardButton(text="🚗 Расчет трансфера (OSRM)", callback_data="menu_transfer")],
        [InlineKeyboardButton(text="🎒 Чек-лист", callback_data="menu_checklist"),
         InlineKeyboardButton(text="📝 Заметки", callback_data="menu_notes")],
        [InlineKeyboardButton(text="🕒 Калькулятор джетлага", callback_data="menu_jetlag"),
         InlineKeyboardButton(text="ℹ️ Аэропортовый гид", callback_data="menu_airport")]
    ])
    return keyboard

@router.message(Command("start"))
async def cmd_start(message: Message):
    text = (
        "✈️ **Привет! Я твой продвинутый тревел-помощник.**\n\n"
        "Работаю на прямых данных Flightradar24, считаю точное время до аэропорта, помогаю бороться с джетлагом и держу под рукой все нужные списки.\n\n"
        "Выбери нужный раздел в меню ниже:"
    )
    await message.answer(text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    try:
        await callback.message.edit_text("Главное меню помощника:", reply_markup=main_menu_keyboard())
    except Exception:
        pass
    await callback.answer()

# ==================== 1. ПОИСК РЕЙСА (FlightRadarAPI) ====================
@router.callback_query(F.data == "menu_flight")
async def flight_menu(callback: CallbackQuery):
    text = (
        "✈️ **Трекинг рейсов**\n\n"
        "Отправь мне номер рейса в чат (например: `S7 5234`, `SU1430`), "
        "и я найду его среди активных бортов на радаре!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.message(F.text.regexp(r"^[A-Z0-9]{2,3}\s?\d{1,4}$"))
async def handle_flight_search(message: Message):
    flight_query = message.text.strip().upper().replace(" ", "")
    status_msg = await message.answer(f"🔍 Сканирую базу активных бортов для рейса `{flight_query}`...", parse_mode="Markdown")
    
    try:
        # Загружаем всю глобальную сетку активных полетов
        all_flights = fr_api.get_flights()
        matching_flights = []
        
        if all_flights:
            # 1. Проверяем полное совпадение в любом из полей объекта
            for f in all_flights:
                dict_repr = str(getattr(f, '__dict__', {})).upper()
                if flight_query in dict_repr:
                    matching_flights.append(f)
            
            # 2. Если не нашли, ищем по цифрам рейса (например, "5234" из "S75234")
            if not matching_flights:
                digits_only = ''.join(filter(str.isdigit, flight_query))
                if len(digits_only) >= 3:
                    for f in all_flights:
                        if digits_only in str(getattr(f, '__dict__', {})).upper():
                            matching_flights.append(f)

        if not matching_flights:
            await status_msg.edit_text(
                f"❌ Рейс `{flight_query}` сейчас не найден в воздухе.\n\n"
                "Самолет может находиться на земле, еще не вылетел или уже завершил полет.",
                parse_mode="Markdown"
            )
            return
        
        flight = matching_flights[0]
        try:
            details = fr_api.get_flight_details(flight)
            flight.set_flight_details(details)
        except Exception:
            pass  # Пропускаем, если детальные данные недоступны
        
        ident = getattr(flight, 'callsign', None) or getattr(flight, 'number', None) or getattr(flight, 'id', None) or flight_query
        origin = getattr(flight, 'origin_airport_name', None) or "Неизвестно"
        dest = getattr(flight, 'destination_airport_name', None) or "Неизвестно"
        status = getattr(flight, 'status_text', None) or "Выполняется"
        lat = getattr(flight, 'latitude', 'Н/Д')
        lon = getattr(flight, 'longitude', 'Н/Д')
        alt = getattr(flight, 'altitude', 'Н/Д')
        speed = getattr(flight, 'ground_speed', 'Н/Д')
        
        response_text = (
            f"✈️ **Найден рейс: {ident}**\n\n"
            f"🛫 **Откуда:** {origin}\n"
            f"🛬 **Куда:** {dest}\n"
            f"📊 **Статус:** {status}\n"
            f"📍 **Координаты:** {lat}, {lon}\n"
            f"📈 **Высота:** {alt} футов\n"
            f"🚀 **Скорость:** {speed} узлов\n\n"
            f"🔗 [Открыть на Flightradar24](https://www.flightradar24.com/{ident})"
        )
        
        storage = get_user_storage(message.from_user.id)
        storage["tracked_flight"] = str(ident)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]])
        await status_msg.edit_text(response_text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
        
    except Exception as e:
        logging.error(f"Error searching flight {flight_query}: {e}")
        await status_msg.edit_text("⚠️ Ошибка при поиске рейса. Попробуй еще раз чуть позже.")

# ==================== 2. РАСЧЕТ ТРАНСФЕРА (OSRM) ====================
@router.callback_query(F.data == "menu_transfer")
async def transfer_menu(callback: CallbackQuery):
    text = (
        "🚗 **Умный расчет трансфера**\n\n"
        "Я могу рассчитать время поездки до аэропорта через OSRM."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Рассчитать тестовый маршрут (Новосибирск)", callback_data="test_osrm")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data == "test_osrm")
async def test_osrm(callback: CallbackQuery):
    url = "http://router.project-osrm.org/route/v1/driving/82.9204,55.0302;82.6506,55.0094?overview=false"
    try:
        res = requests.get(url, timeout=5).json()
        if "routes" in res and len(res["routes"]) > 0:
            route = res["routes"][0]
            duration_mins = round(route["duration"] / 60)
            distance_km = round(route["distance"] / 1000, 1)
            
            buffer_mins = 120
            total_time = duration_mins + buffer_mins
            
            text = (
                f"🚗 **Расчет маршрута (Центр ➔ Толмачево OVB):**\n\n"
                f"📏 Расстояние: **{distance_km} км**\n"
                f"⏱ Чистое время в пути: **~{duration_mins} мин**\n"
                f"🛡 Рекомендуемый буфер на досмотр: **{buffer_mins} мин**\n"
                f"⏰ **Итого заложено времени:** ~{total_time} мин"
            )
        else:
            text = "⚠️ Сервер OSRM вернул пустой маршрут."
    except Exception:
        text = "⚠️ Не удалось связаться с картографическим сервисом OSRM."
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

# ==================== 3. ЧЕК-ЛИСТ И ЗАМЕТКИ ====================
@router.callback_query(F.data == "menu_checklist")
async def checklist_menu(callback: CallbackQuery):
    storage = get_user_storage(callback.from_user.id)
    cl = storage["checklist"]
    
    text = "🎒 **Твой чек-лист вещей:**\n\n"
    buttons = []
    for item, status in cl.items():
        icon = "✅" if status else "⭕️"
        text += f"{icon} {item}\n"
        buttons.append([InlineKeyboardButton(text=f"Переключить: {item}", callback_data=f"toggle_{item}")])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_"))
async def toggle_item(callback: CallbackQuery):
    item = callback.data.replace("toggle_", "")
    storage = get_user_storage(callback.from_user.id)
    if item in storage["checklist"]:
        storage["checklist"][item] = not storage["checklist"][item]
    
    cl = storage["checklist"]
    text = "🎒 **Твой чек-лист вещей:**\n\n"
    buttons = []
    for it, status in cl.items():
        icon = "✅" if status else "⭕️"
        text += f"{icon} {it}\n"
        buttons.append([InlineKeyboardButton(text=f"Переключить: {it}", callback_data=f"toggle_{it}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data == "menu_notes")
async def notes_menu(callback: CallbackQuery):
    storage = get_user_storage(callback.from_user.id)
    text = f"📝 **Твои заметки и брони:**\n\n{storage['notes']}\n\n*(Чтобы изменить, отправь текст с префиксом `/note Твой текст`)*"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@router.message(Command("note"))
async def save_note(message: Message):
    new_note = message.text.replace("/note", "").strip()
    if not new_note:
        await message.answer("⚠️ Текст заметки не может быть пустым. Пример: `/note Отель забронирован`", parse_mode="Markdown")
        return
    storage = get_user_storage(message.from_user.id)
    storage["notes"] = new_note
    await message.answer(f"✅ Заметка успешно сохранена:\n\n{new_note}")

# ==================== 4. ДЖЕТЛАГ И АЭРОПОРТЫ ====================
@router.callback_query(F.data == "menu_jetlag")
async def jetlag_menu(callback: CallbackQuery):
    text = (
        "🕒 **Калькулятор джетлага и адаптации**\n\n"
        "1. **Режим сна:** За день до вылета смести режим на 1 час ближе к поясу назначения.\n"
        "2. **Вода:** Пей больше воды во время полета, избегай кофе и алкоголя.\n"
        "3. **Свет:** По прилёте сразу выйди на дневной свет."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data == "menu_airport")
async def airport_menu(callback: CallbackQuery):
    text = (
        "ℹ️ **Аэропортовый гид и лайфхаки**\n\n"
        "• **Вода:** Возьми пустую бутылку и набери в питьевом фонтанчике после досмотра.\n"
        "• **Розетки:** Самые свободные розетки — у дальних гейтов.\n"
        "• **Багаж:** Делай фото чемодана перед сдачей."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

# Flask заглушка для Render
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    asyncio.run(main())
