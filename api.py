import aiohttp
import os

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

async def get_flight_info(flight_number: str):
    flight_number = flight_number.upper()
    # Демо-данные (сюда потом можно подключить реальное API)
    return {
        "flight": flight_number,
        "airline": "Аэрофлот",
        "status": "В полёте 🟢",
        "departure_airport": "Шереметьево (SVO)",
        "arrival_airport": "Пулково (LED)",
        "departure_time": "12:30 (МСК)",
        "arrival_time": "13:55 (МСК)",
        "duration": "1ч 25м",
        "gate": "C14",
        "terminal": "B",
        "aircraft": "Airbus A320",
        "arr_city_code": "St Petersburg"
    }

async def get_airport_board(airport_code: str):
    """
    Генерирует список рейсов для интерактивного табло аэропорта
    """
    airport_code = airport_code.upper()
    # Демо-список рейсов для табло
    return [
        {"flight": "SU-1234", "dest": "Санкт-Петербург", "time": "14:15", "status": "По расписанию"},
        {"flight": "SU-5678", "dest": "Сочи", "time": "14:40", "status": "Задерживается"},
        {"flight": "S7-2026", "dest": "Новосибирск", "time": "15:10", "status": "Посадка"}
    ]

async def get_weather(city_name: str):
    """
    Получение реальной погоды через OpenWeatherMap
    """
    if not WEATHER_API_KEY:
        return "⛅️ Погода: +22°C, переменная облачность"
    
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&units=metric&appid={WEATHER_API_KEY}&lang=ru"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]
                    return f"🌡 Погода в точке прилета: {temp}°C, {desc}"
        except Exception:
            pass
        return "⛅️ Данные о погоде временно недоступны"
