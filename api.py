import aiohttp
import os

# Получаем ключи из переменных окружения
AVIATION_API_KEY = os.getenv("AVIATION_API_KEY", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

async def get_flight_info(flight_number: str):
    """
    Запрос информации о рейсе. 
    Здесь можно подключить выбранное API (например, AeroDataBox через RapidAPI).
    """
    # Пока возвращаем структурированный пример, который легко заменится на реальный JSON от API
    flight_number = flight_number.upper()
    
    # Демо-данные для теста верстки и логики
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
        "dep_city_code": "SVO",
        "arr_city_code": "LED"
    }

async def get_weather(city_code: str):
    """
    Получение погоды в аэропорту по его коду или названию через OpenWeatherMap
    """
    if not WEATHER_API_KEY:
        return "⛅️ Погода: +20°C, ясно (демо-режим)"
    
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_code}&units=metric&appid={WEATHER_API_KEY}&lang=ru"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]
                    return f"🌡 Погода ({city_code}): {temp}°C, {desc}"
        except Exception:
            pass
        return "⛅️ Данные о погоде временно недоступны"
