import asyncio
import logging
import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from FlightRadarAPI import FlightRadar24API
import requests

# Инициализация логгирования и бота
logging.basicConfig(level=logging.INFO)
TOKEN = "8987889905:AAEV-fUDPxQAPzd7DnTKhDS_HGno3rBcnfA"  # Вставь свой токен Telegram-бота

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

fr_api = FlightRadarAPI()

# Простейшее хранилище в памяти для демонстрации (чек-листы, заметки, избранное)
user_data_storage = {}

def get_user_storage(user_id: int):
    if user_id not in user_data_storage:
        user_data_storage[user_id] = {
            "checklist": {"Паспорт": False, "Билеты": False, "Зарядка": False, "Аптечка": False},
            "notes": "Пока нет записей.",
            "tracked_flight": None
        }
    return user_data_storage[user_id]

# Главное меню с инлайн-кнопками
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
    await callback.message.edit_text(" główное меню помощника:", reply_markup=main_menu_keyboard())
    await callback.answer()

# ==================== 1. ПОИСК РЕЙСА (FlightRadarAPI) ====================
@router.callback_query(F.data == "menu_flight")
async def flight_menu(callback: CallbackQuery):
    text = (
        "✈️ **Трекинг рейсов**\n\n"
        "Отправь мне номер рейса в чат (например: `SU-1430`, `AFL1430` или `S7 3020`), "
        "и я запрошу актуальные данные с радара в реальном времени!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.message(F.text.regexp(r"^[A-Z0-9]{2,3}\s?\d{1,4}$"))
async def handle_flight_search(message: Message):
    flight_query = message.text.strip().upper().replace(" ", "")
    await message.answer(f"🔍 Ищу рейс `{flight_query}` на Flightradar24...", parse_mode="Markdown")
    
    try:
        flights = fr_api.get_flights(query=flight_query)
        if not flights:
            await message.answer("❌ Рейс не найден или самолет сейчас не в воздухе / не выполняет полет. Проверь номер.")
            return
        
        flight = flights[0]
        details = fr_api.get_flight_details(flight)
        flight.set_flight_details(details)
        
        # Сбор данных
        ident = flight.get_flight_identification()
        origin = flight.origin_airport_name or "Неизвестно"
        dest = flight.destination_airport_name or "Неизвестно"
        status = flight.status_text or "Выполняется"
        lat = flight.latitude
        lon = flight.longitude
        alt = flight.altitude
        speed = flight.ground_speed
        
        response_text = (
            f"✈️ **Рейс: {ident}**\n\n"
            f"🛫 **Откуда:** {origin}\n"
            f"🛬 **Куда:** {dest}\n"
            f"📊 **Статус:** {status}\n"
            f"📍 **Координаты:** {lat}, {lon}\n"
            f"📈 **Высота:** {alt} футов\n"
            f"🚀 **Скорость:** {speed} узлов\n\n"
            f"🔗 [Открыть на Flightradar24](https://www.flightradar24.com/{ident})"
        )
        
        # Сохраняем в избранное пользователя
        storage = get_user_storage(message.from_user.id)
        storage["tracked_flight"] = ident
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]])
        await message.answer(response_text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
        
    except Exception as e:
        logging.error(f"Error fetching flight: {e}")
        await message.answer("⚠️ Ошибка при запросе данных к Flightradar24. Попробуй позже.")

# ==================== 2. РАСЧЕТ ТРАНСФЕРА (OSRM) ====================
@router.callback_query(F.data == "menu_transfer")
async def transfer_menu(callback: CallbackQuery):
    text = (
        "🚗 **Умный расчет трансфера**\n\n"
        "Я могу рассчитать время поездки до аэропорта через OSRM. "
        "Отправь координаты или в разработке: расчет из твоего города."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Рассчитать тестовый маршрут (Новосибирск)", callback_data="test_osrm")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "test_osrm")
async def test_osrm(callback: CallbackQuery):
    # Тестовые координаты: Центр Новосибирска -> Аэропорт Толмачево (OVB)
    # OSRM public API demo
    url = "http://router.project-osrm.org/route/v1/driving/82.9204,55.0302;82.6506,55.0094?overview=false"
    try:
        res = requests.get(url, timeout=5).json()
        route = res["routes"][0]
        duration_mins = round(route["duration"] / 60)
        distance_km = round(route["distance"] / 1000, 1)
        
        buffer_mins = 120 # 2 часа досмотр
        total_time = duration_mins + buffer_mins
        
        text = (
            f"🚗 **Расчет маршрута (Центр ➔ Толмачево OVB):**\n\n"
            f"📏 Расстояние: **{distance_km} км**\n"
            f"⏱ Чистое время в пути: **~{duration_mins} мин**\n"
            f"🛡 Рекомендуемый буфер на досмотр: **{buffer_mins} мин**\n"
            f"⏰ **Итого заложено времени:** ~{total_time} мин (выезжай заблаговременно!)"
        )
    except Exception:
        text = "⚠️ Не удалось связаться с картографическим сервисом OSRM."
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
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
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_"))
async def toggle_item(callback: CallbackQuery):
    item = callback.data.replace("toggle_", "")
    storage = get_user_storage(callback.from_user.id)
    if item in storage["checklist"]:
        storage["checklist"][item] = not storage["checklist"][item]
    
    # Перерисовываем чек-лист
    cl = storage["checklist"]
    text = "🎒 **Твой чек-лист вещей:**\n\n"
    buttons = []
    for it, status in cl.items():
        icon = "✅" if status else "⭕️"
        text += f"{icon} {it}\n"
        buttons.append([InlineKeyboardButton(text=f"Переключить: {it}", callback_data=f"toggle_{it}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_notes")
async def notes_menu(callback: CallbackQuery):
    storage = get_user_storage(callback.from_user.id)
    text = f"📝 **Твои заметки и брони:**\n\n{storage['notes']}\n\n*(Чтобы изменить, отправь текст с префиксом `/note Твой текст`)*"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.message(Command("note"))
async def save_note(message: Message):
    new_note = message.text.replace("/note", "").strip()
    storage = get_user_storage(message.from_user.id)
    storage["notes"] = new_note
    await message.answer(f"✅ Заметка успешно сохранена:\n\n{new_note}")

# ==================== 4. НОВЫЕ ФИЧИ: ДЖЕТЛАГ И АЭРОПОРТЫ ====================
@router.callback_query(F.data == "menu_jetlag")
async def jetlag_menu(callback: CallbackQuery):
    text = (
        "🕒 **Калькулятор джетлага и адаптации**\n\n"
        "Перелетаешь в другой часовой пояс? Вот базовые правила быстрой перестройки:\n"
        "1. **Спинокен контроль:** За день до вылета смести режим сна на 1 час ближе к часовому поясу назначения.\n"
        "2. **Вода:** Пей больше чистой воды во время полета, избегай алкоголя и тяжелого кофе.\n"
        "3. **Солнечный свет:** По прилёте сразу выйди на дневной свет — это главный биологический будильник для мозга."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_airport")
async def airport_menu(callback: CallbackQuery):
    text = (
        "ℹ️ **Аэропортовый гид и лайфхаки**\n\n"
        "• **Питьевая вода:** Не покупай воду до досмотра задорого. Возьми пустую пластиковую бутылку и набери в питьевом фонтанчике после зоны контроля.\n"
        "• **Зарядки:** Самые свободные розетки обычно возле выходов на посадку (гейтов) в дальних секторах терминала.\n"
        "• **Багаж:** Делай фото чемодана перед сдачей на стойку регистрации на случай споров о сохранности."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
