import asyncio
import logging
import sys
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, add_subscription, get_subscribers
from api import get_flight_info, get_weather

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message, command: CommandObject):
    args = command.args # Сюда прилетит параметр, если перешли по ссылке вида t.me/bot?start=flight_SU1234
    
    if args and args.startswith("flight_"):
        flight_num = args.split("_")[1].upper()
        # Регистрируем подписчика (родителя)
        await add_subscription(flight_num, message.from_user.id, message.from_user.id)
        
        await message.answer(
            f"🔗 Вы успешно подписались на отслеживание рейса <b>{flight_num}</b>!\n"
            "Я буду присылать вам все актуальные обновления."
        )
        # Сразу показываем информацию по рейсу
        await show_flight_card(message, flight_num)
        return

    # Обычный старт
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✈️ Ввести номер рейса", callback_data="enter_flight")],
        [InlineKeyboardButton(text="📊 Табло аэропорта", callback_data="airport_board")]
    ])
    
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}! ✈️\n"
        "Я твой личный тревел-ассистент. Помогу отследить полеты, узнать погоду и поделюсь информацией с близкими.",
        reply_markup=keyboard
    )

async def show_flight_card(message: Message, flight_num: str):
    data = await get_flight_info(flight_num)
    weather_arr = await get_weather(data["arr_city_code"])
    
    # Генерируем ссылку для шаринга родителям
    bot_info = await bot.get_me()
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
    
    share_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍👩‍👧 Поделиться с родителями", url=f"https://t.me/share/url?url={share_link}&text=Следи за моим полетом в реальном времени!")]
    ])
    
    await message.answer(response_html, reply_markup=share_keyboard)

@dp.message(F.text)
async def track_flight(message: Message):
    flight_num = message.text.strip()
    await show_flight_card(message, flight_num)

# Веб-сервер для Render (предотвращает засыпание бота)
async def handle(request):
    return web.Response(text="Flight Bot is active and running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    await init_db()
    await web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
