import os
import aiohttp

AIRPORT_DATA = {
    "SVO": {"coords": (55.9726, 37.4146), "name": "Шереметьево (Москва)"},
    "DME": {"coords": (55.4088, 37.9063), "name": "Домодедово (Москва)"},
    "VKO": {"coords": (55.5915, 37.2615), "name": "Внуково (Москва)"},
    "LED": {"coords": (59.8003, 30.2625), "name": "Пулково (Санкт-Петербург)"},
    "OVB": {"coords": (55.0126, 82.6507), "name": "Толмачево (Новосибирск)"},
    "DXB": {"coords": (25.2532, 55.3657), "name": "Дубай"},
    "AYT": {"coords": (36.8987, 30.8005), "name": "Анталья"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

async def get_flight_info(flight_number: str):
    raw_flight = flight_number.upper().replace(" ", "").replace("-", "")
    return {
        "flight": raw_flight,
        "airline": "Авиакомпания",
        "status": "Актуальный статус на Flightradar24",
        "departure_airport": "Уточняется",
        "departure_iata": "OVB",
        "arrival_airport": "Уточняется",
        "arrival_iata": "DME",
        "departure_time": "--:--",
        "arrival_time": "--:--",
        "dep_gate": "—",
        "dep_terminal": "—",
        "arr_gate": "—",
        "arr_terminal": "—",
        "tz_diff": "",
        "fr24_link": f"https://www.flightradar24.com/data/flights/{raw_flight.lower()}",
        "arr_query_for_weather": "Москва"
    }

async def get_airport_board(airport_code: str):
    code = airport_code.upper().strip()
    board_list = []

    # Пробуем запросить через публичный JSON-эндпоинт Яндекс Расписаний
    url = f"https://rasp.yandex.ru/informers/airport/{code}/board.json"
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Парсим секцию вылетов, если она есть в ответе яндекса
                    departures = data.get("schedule", {}).get("departures", [])
                    for item in departures:
                        thread = item.get("thread", {})
                        f_num = thread.get("number") or thread.get("short_title", "Рейс")
                        dest = item.get("to", {}).get("title", "Назначение")
                        time_val = item.get("departure", "")
                        
                        if "T" in time_val:
                            time_str = time_val.split("T")[1][:5]
                        elif ":" in time_val:
                            time_str = time_val[:5]
                        else:
                            time_str = "--:--"

                        board_list.append({
                            "flight": str(f_num),
                            "dest": str(dest),
                            "time": str(time_str),
                            "sort_key": str(time_str)
                        })
        except Exception as e:
            print(f"API board fetch error for {code}: {e}")

    # Если Яндекс отдал пустой ответ или заблокировал, возвращаем пустой массив, 
    # а не фейковые рейсы, чтобы бот честно сказал, что табло временно недоступно.
    if board_list:
        board_list.sort(key=lambda x: x["sort_key"])
        
    return board_list

async def get_weather(location: str):
    if not location:
        return "Погода недоступна"
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
        return "🌡 Погода: не удалось определить место"

    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(weather_url, timeout=5) as resp:
                if resp.status == 200:
                    temp = (await resp.json()).get("current_weather", {}).get("temperature")
                    if temp is not None:
                        return f"🌡 Температура в пункте назначения: {round(temp)}°C"
        except Exception:
            pass
    return "🌡 Погода: ошибка получения данных"

async def calculate_real_transfer(address: str, airport_code: str = "OVB"):
    airport_code = airport_code.upper().strip()
    a_lat, a_lon = AIRPORT_DATA.get(airport_code, {}).get("coords", (55.0126, 82.6507))

    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={address}&count=1"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(geo_url, timeout=5) as resp:
                if resp.status == 200:
                    results = (await resp.json()).get("results")
                    if results:
                        d_lat, d_lon = results[0]["latitude"], results[0]["longitude"]
                    else:
                        return None
        except Exception:
            return None

    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{a_lon},{a_lat};{d_lon},{d_lat}?overview=false"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(osrm_url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    routes = data.get("routes", [])
                    if routes:
                        duration_sec = routes[0]["duration"]
                        distance_m = routes[0]["distance"]
                        
                        duration_min = int(duration_sec / 60)
                        distance_km = round(distance_m / 1000, 1)
                        
                        hours = duration_min // 60
                        mins = duration_min % 60
                        t_str = f"{hours} ч. {mins} мин." if hours > 0 else f"{mins} мин."
                        
                        return {
                            "distance": distance_km,
                            "time_str": t_str,
                            "total_minutes": duration_min
                        }
        except Exception as e:
            print(f"OSRM Error: {e}")
            
    return None

def get_airport_details(airport_code: str):
    airport_code = airport_code.upper().strip()
    name = AIRPORT_DATA.get(airport_code, {}).get("name", airport_code)
    return f"🏢 <b>Аэропорт:</b> {name}"
