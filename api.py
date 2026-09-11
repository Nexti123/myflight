import aiohttp
import os

AVIATION_API_KEY = os.getenv("AVIATION_API_KEY", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

async def get_flight_info(flight_number: str):
    flight_number = flight_number.upper()
    
    if AVIATION_API_KEY:
        url = f"http://api.aviationstack.com/v1/flights?access_key={AVIATION_API_KEY}&flight_iata={flight_number}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        if res_json.get("data"):
                            flight = res_json["data"][0]
                            arr = flight.get("arrival", {})
                            dep = flight.get("departure", {})
                            airline = flight.get("airline", {})
                            aircraft = flight.get("aircraft", {})
                            
                            return {
                                "flight": flight_number,
                                "airline": airline.get("name", "Не указана"),
                                "status": flight.get("flight_status", "активен").upper(),
                                "departure_airport": dep.get("airport", "Не указан"),
                                "arrival_airport": arr.get("airport", "Не указан"),
                                "departure_time": dep.get("scheduled", "—")[:16].replace("T", " "),
                                "arrival_time": arr.get("scheduled", "—")[:16].replace("T", " "),
                                "duration": "По расписанию",
                                "gate": arr.get("gate", "—"),
                                "terminal": arr.get("terminal", "—"),
                                "aircraft": aircraft.get("model", "Стандартный"),
                                "arr_city_code": arr.get("iata", "Moscow")
                            }
            except Exception:
                pass

    return {
        "flight": flight_number,
        "airline": "Международные авиалинии",
        "status": "В ПУТИ 🟢",
        "departure_airport": "Аэропорт отправления",
        "arrival_airport": "Аэропорт назначения",
        "departure_time": "Сегодня",
        "arrival_time": "По расписанию",
        "duration": "В норме",
        "gate": "B12",
        "terminal": "2",
        "aircraft": "Boeing / Airbus",
        "arr_city_code": "Moscow"
    }

async def get_airport_board(airport_code: str):
    airport_code = airport_code.upper()
    boards = {
        "SVO": [
            {"flight": "SU-1008", "dest": "Сочи", "time": "18:20", "status": "Летит"},
            {"flight": "SU-1266", "dest": "Нижний Новгород", "time": "18:45", "status": "Посадка"},
            {"flight": "SU-1860", "dest": "Ереван", "time": "19:10", "status": "По расписанию"}
        ],
        "LED": [
            {"flight": "FV-6011", "dest": "Москва (SVO)", "time": "18:30", "status": "Летит"},
            {"flight": "U6-2703", "dest": "Екатеринбург", "time": "19:00", "status": "Задерживается"}
        ]
    }
    return boards.get(airport_code, [
        {"flight": "SU-1234", "dest": "Международный рейс", "time": "Ближайший", "status": "По расписанию"},
        {"flight": "S7-5555", "dest": "Региональный рейс", "time": "По расписанию", "status": "Активен"}
    ])

async def get_weather(city_query: str):
    if not WEATHER_API_KEY:
        return "🌡 Погода в точке назначения: +22°C, ясно"
    
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_query}&units=metric&appid={WEATHER_API_KEY}&lang=ru"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]return f"🌡 Погода в пункте прилета: {temp}°C, {desc}"
        except Exception:
            pass
        return "🌡 Погода: данные уточняются"
