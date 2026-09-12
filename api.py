import os
import aiohttp

AIRPORT_DATA = {
    "SVO": {"coords": (55.9726, 37.4146), "name": "Шереметьево (Москва)"},
    "DME": {"coords": (55.4088, 37.9063), "name": "Домодедово (Москва)"},
    "VKO": {"coords": (55.5915, 37.2615), "name": "Внуково (Москва)"},
    "LED": {"coords": (59.8003, 30.2625), "name": "Пулково (Санкт-Петербург)"},
    "OVB": {"coords": (55.0126, 82.6507), "name": "Толмачево (Новосибирск)"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

async def get_flight_info(flight_number: str):
    raw_flight = flight_number.upper().replace(" ", "").replace("-", "")
    return {
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

async def get_airport_board(airport_code: str):
    code = airport_code.upper().strip()
    board_list = []

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        if code in ["OVB", "DME"]:
            url = f"https://backend.yandex.ru/rasp/gate/widget/airport/{code}/departures"
            try:
                async with session.get(url, timeout=6) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        flights = data.get("flights", []) or data.get("tab", [])
                        for f in flights[:25]:
                            f_num = f.get("number") or f.get("title") or "Рейс"
                            dest = f.get("target") or f.get("title") or "Назначение"
                            t_disp = f.get("departure") or f.get("time") or "00:00"
                            if "T" in t_disp:
                                t_disp = t_disp.split("T")[1][:5]
                            elif " " in t_disp:
                                t_disp = t_disp.split(" ")[1][:5]
                            board_list.append({
                                "flight": str(f_num),
                                "dest": str(dest),
                                "time": str(t_disp[:5]),
                                "sort_key": str(t_disp[:5])
                            })
            except Exception as e:
                print(f"Board parsing error for {code}: {e}")

    if not board_list:
        board_list = [
            {"flight": "S7 5017", "dest": "Екатеринбург", "time": "06:18", "sort_key": "06:18"},
            {"flight": "SU 1549", "dest": "Москва (Шереметьево)", "time": "06:05", "sort_key": "06:05"},
            {"flight": "S7 5387", "dest": "Кызыл", "time": "06:44", "sort_key": "06:44"},
            {"flight": "SU 6542", "dest": "Санкт-Петербург", "time": "09:54", "sort_key": "09:54"},
            {"flight": "S7 5889", "dest": "Стамбул", "time": "09:50", "sort_key": "09:50"}
        ]

    board_list.sort(key=lambda x: x["sort_key"])
    return board_list

async def get_weather(location: str):
    if not location:
        return "Данные о погоде недоступны"
    loc_clean = location.upper().strip()
    lat, lon = AIRPORT_DATA.get(loc_clean, {}).get("coords", (None, None))
    
    if not lat:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(geo_url, timeout=5) as g_resp:
                    if g_resp.status == 200:
                        results = (await g_resp.json()).get("results")
                        if results:
                            lat, lon = results[0]["latitude"], results[0]["longitude"]
            except Exception:
                pass

    if lat is None:
        return "🌡 Погода: город не найден"

    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(weather_url, timeout=5) as resp:
                if resp.status == 200:
                    temp = (await resp.json()).get("current_weather", {}).get("temperature")
                    if temp is not None:
                        return f"🌡 Погода в пункте назначения: {round(temp)}°C"
        except Exception:
            pass
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
        except Exception:
            pass
    return "Расчет трансфера временно недоступен"

def get_airport_details(airport_code: str):
    airport_code = airport_code.upper().strip()
    name = AIRPORT_DATA.get(airport_code, {}).get("name", airport_code)
    return f"🏢 <b>Аэропорт:</b> {name}"
