import os
import aiohttp
from datetime import datetime

# Координаты для трансфера и погоды
AIRPORT_DATA = {
    "SVO": {"coords": (55.9726, 37.4146), "name": "Шереметьево (Москва)"},
    "DME": {"coords": (55.4088, 37.9063), "name": "Домодедово (Москва)"},
    "VKO": {"coords": (55.5915, 37.2615), "name": "Внуково (Москва)"},
    "LED": {"coords": (59.8003, 30.2625), "name": "Пулково (Санкт-Петербург)"},
    "OVB": {"coords": (55.0126, 82.6507), "name": "Толмачево (Новосибирск)"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

async def get_flight_info(flight_number: str):
    """Поиск данных по конкретному рейсу с прямым переходом на Flightradar24"""
    raw_flight = flight_number.upper().replace(" ", "").replace("-", "")
    
    result = {
        "flight": raw_flight,
        "airline": "Авиакомпания",
        "status": "Отслеживается на Flightradar24 ✈️",
        "departure_airport": "Информация уточняется",
        "departure_iata": "",
        "arrival_airport": "Информация уточняется",
        "arrival_iata": "",
        "departure_time": "См. в табло",
        "arrival_time": "См. в табло",
        "dep_gate": "Не указан",
        "dep_terminal": "Не указан",
        "arr_gate": "Не указан",
        "arr_terminal": "Не указан",
        "tz_diff": "Часовые пояса",
        "fr24_link": f"https://www.flightradar24.com/data/flights/{raw_flight.lower()}",
        "arr_query_for_weather": ""
    }
    return result

async def get_airport_board(airport_code: str):
    """Официальное табло Толмачево (OVB) и Домодедово (DME)"""
    code = airport_code.upper().strip()
    board_list = []

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # === ТОЛМАЧЕВО (OVB) ===
        if code == "OVB":
            url = "https://tolmachevo.ru/api/passengers/board/departures/"
            try:
                async with session.get(url, timeout=8) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("items", []) or data.get("flights", [])
                        for f in items[:30]:
                            f_num = f.get("flight") or f.get("number") or "Рейс"
                            dest = f.get("destination") or f.get("city") or "Назначение"
                            t_disp = f.get("time_scheduled") or f.get("time") or "00:00"
                            if "T" in t_disp:
                                t_disp = t_disp.split("T")[1][:5]
                            elif " " in t_disp:
                                t_disp = t_disp.split(" ")[1][:5]
                            
                            board_list.append({
                                "flight": f_num,
                                "dest": dest,
                                "time": t_disp,
                                "sort_key": t_disp
                            })
            except Exception as e:
                print(f"OVB Board Error: {e}")

        # === ДОМОДЕДОВО (DME) ===
        elif code == "DME":
            url = "https://www.dme.ru/live-board/api/departures/"
            try:
                async with session.get(url, timeout=8) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for f in data.get("flights", [])[:30]:
                            f_num = f.get("flight_number", "Рейс")
                            dest = f.get("destination_name", "Назначение")
                            t_disp = f.get("time_scheduled", "00:00")[:5]
                            board_list.append({
                                "flight": f_num,
                                "dest": dest,
                                "time": t_disp,
                                "sort_key": t_disp
                            })
            except Exception as e:
                print(f"DME Board Error: {e}")

    board_list.sort(key=lambda x: x["sort_key"])
    return board_list

async def get_weather(location: str):
    if not location:
        return "Данные о погоде недоступны"
    loc_clean = location.upper().strip()
    lat, lon = None, None
    if loc_clean in AIRPORT_DATA:
        lat, lon = AIRPORT_DATA[loc_clean]["coords"]
    else:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(geo_url, timeout=5) as g_resp:
                    if g_resp.status == 200:
                        g_data = await g_resp.json()
                        results = g_data.get("results")
                        if results:
                            lat, lon = results[0]["latitude"], results[0]["longitude"]
            except Exception as e:
                print(f"Geocoding error: {e}")

    if lat is None or lon is None:
        return "🌡 Погода: город не найден"

    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(weather_url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    temp = data.get("current_weather", {}).get("temperature")
                    if temp is not None:
                        return f"🌡 Погода в пункте назначения: {round(temp)}°C"
        except Exception as e:
            print(f"Weather error: {e}")
    return "🌡 Погода: данные недоступны"

async def calculate_real_transfer(airport_code: str, address: str = "Центр города"):
    if not airport_code:
        return "Не удалось рассчитать трансфер"
    airport_code = airport_code.upper().strip()
    a_lat, a_lon = AIRPORT_DATA.get(airport_code, {}).get("coords", (None, None))
    if not a_lat:
        return "Расчет трансфера: аэропорт не найден"

    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={address}&count=1"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(geo_url, timeout=5) as resp:
                if resp.status == 200:
                    results = (await resp.json()).get("results")
                    if results:
                        d_lat, d_lon = results[0]["latitude"], results[0]["longitude"]
                    else:
                        d_lat, d_lon = a_lat + 0.15, a_lon + 0.15
        except Exception:
            d_lat, d_lon = a_lat + 0.15, a_lon + 0.15

    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{a_lon},{a_lat};{d_lon},{d_lat}?overview=false"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(osrm_url, timeout=5) as resp:
                if resp.status == 200:
                    routes = (await resp.json()).get("routes", [])
                    if routes:
                        duration_min = int(routes[0]["duration"] / 60)
                        distance_km = round(routes[0]["distance"] / 1000, 1)
                        return f"🚗 Трансфер на авто: ~{duration_min} мин ({distance_km} км)"
        except Exception as e:
            print(f"OSRM error: {e}")
    return "Расчет трансфера временно недоступен"

def get_airport_details(airport_code: str):
    airport_code = airport_code.upper().strip()
    name = AIRPORT_DATA.get(airport_code, {}).get("name", airport_code)
    return f"🏢 <b>Аэропорт:</b> {name}"
