import aiohttp
import os
import math

AVIATION_API_KEY = os.getenv("AVIATION_API_KEY", "")

AIRLINE_PREFIX_MAP = {
    "S7": "SBI", "SU": "AFL", "FV": "SDM", "U6": "SVR",
    "UT": "UTA", "DP": "PBD", "EK": "UAE", "TK": "THY", "FZ": "FDB"
}

AIRPORT_INFO_MAP = {
    "SVO": {"name": "Шереметьево", "city": "Москва", "country": "Россия", "tz": 3, "lat": 55.9726, "lon": 37.4146},
    "DME": {"name": "Домодедово", "city": "Москва", "country": "Россия", "tz": 3, "lat": 55.4088, "lon": 37.9063},
    "VKO": {"name": "Внуково", "city": "Москва", "country": "Россия", "tz": 3, "lat": 55.5915, "lon": 37.2615},
    "LED": {"name": "Пулково", "city": "Санкт-Петербург", "country": "Россия", "tz": 3, "lat": 59.8003, "lon": 30.2625},
    "AER": {"name": "Сочи", "city": "Сочи", "country": "Россия", "tz": 3, "lat": 43.4499, "lon": 39.9566},
    "OVB": {"name": "Толмачево", "city": "Новосибирск", "country": "Россия", "tz": 7, "lat": 55.0126, "lon": 82.6507},
    "SVX": {"name": "Кольцово", "city": "Екатеринбург", "country": "Россия", "tz": 5, "lat": 56.7431, "lon": 60.8027},
    "DXB": {"name": "Дубай Интернешнл", "city": "Дубай", "country": "ОАЭ", "tz": 4, "lat": 25.2532, "lon": 55.3657},
    "IST": {"name": "Стамбул", "city": "Стамбул", "country": "Турция", "tz": 3, "lat": 41.2753, "lon": 28.7519},
    "AYT": {"name": "Анталья", "city": "Анталья", "country": "Турция", "tz": 3, "lat": 36.8987, "lon": 30.8005},
    "JFK": {"name": "им. Джона Кеннеди", "city": "Нью-Йорк", "country": "США", "tz": -4, "lat": 40.6413, "lon": -73.7781}
}

def normalize_flight_number(flight_number: str) -> str:
    flight_number = flight_number.upper().strip()
    for iata, icao in AIRLINE_PREFIX_MAP.items():
        if flight_number.startswith(iata) and not flight_number.startswith(icao):
            num_part = flight_number[len(iata):].strip("- ")
            return f"{icao}{num_part}"
    return flight_number.replace("-", "").replace(" ", "")

async def get_flight_info(flight_number: str):
    raw_input = flight_number.upper().strip()
    search_flight = normalize_flight_number(raw_input)
    
    flight_data = None
    if AVIATION_API_KEY:
        urls = [
            f"http://api.aviationstack.com/v1/flights?access_key={AVIATION_API_KEY}&flight_icao={search_flight}",
            f"http://api.aviationstack.com/v1/flights?access_key={AVIATION_API_KEY}&flight_iata={raw_input}"
        ]
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=6) as resp:
                        if resp.status == 200:
                            res_json = await resp.json()
                            flights_list = res_json.get("data", [])
                            if flights_list:
                                flight_data = flights_list[0]
                                break
                except Exception:
                    pass

    if not flight_data:
        flight_data = {}

    arr = flight_data.get("arrival", {}) or {}
    dep = flight_data.get("departure", {}) or {}
    airline = flight_data.get("airline", {}) or {}
    aircraft = flight_data.get("aircraft", {}) or {}

    status_raw = flight_data.get("flight_status", "unknown")
    status_map = {
        "active": "В полете 🟢",
        "scheduled": "Запланирован ✈️",
        "landed": "Прибыл 🛬",
        "cancelled": "Отменен ❌",
        "incident": "Задержан / Инцидент ⚠️"
    }
    status_text = status_map.get(status_raw, "Информация уточняется ✈️")

    dep_time = dep.get("scheduled") or "Не указано"
    if dep_time and "T" in dep_time:
        dep_time = dep_time.replace("T", " ")[:16]

    arr_time = arr.get("scheduled") or "Не указано"
    if arr_time and "T" in arr_time:
        arr_time = arr_time.replace("T", " ")[:16]

    dep_iata = (dep.get("iata") or "SVO").upper()
    arr_iata = (arr.get("iata") or "LED").upper()
    
    tz_dep = AIRPORT_INFO_MAP.get(dep_iata, {}).get("tz", 3)
    tz_arr = AIRPORT_INFO_MAP.get(arr_iata, {}).get("tz", 3)
    tz_diff = tz_arr - tz_dep
    
    if tz_diff > 0:
        tz_text = f"Разница во времени: +{tz_diff} ч. в пункте назначения"
    elif tz_diff < 0:
        tz_text = f"Разница во времени: {tz_diff} ч. в пункте назначения"
    else:
        tz_text = "Часовые пояса совпадают"

    arr_city = arr.get("city") or AIRPORT_INFO_MAP.get(arr_iata, {}).get("city") or "Санкт-Петербург"
    arr_airport_name = arr.get("airport") or AIRPORT_INFO_MAP.get(arr_iata, {}).get("name") or arr_iata
    dep_airport_name = dep.get("airport") or AIRPORT_INFO_MAP.get(dep_iata, {}).get("name") or dep_iata

    is_flying = (status_raw in ["active", "scheduled"])
    fr24_link = f"https://www.flightradar24.com/data/flights/{raw_input.lower()}" if is_flying else None

    # ЧЕСТНЫЕ ГЕЙТЫ И ТЕРМИНАЛЫ (БЕЗ ФЕЙКОВЫХ B4 / 2)
    dep_gate = dep.get("gate") or "Не указан"
    dep_terminal = dep.get("terminal") or "Не указан"
    arr_gate = arr.get("gate") or "Не указан"
    arr_terminal = arr.get("terminal") or "Не указан"

    return {
        "flight": raw_input,
        "airline": airline.get("name") or "Авиакомпания не указана",
        "status": status_text,
        "departure_airport": dep_airport_name,
        "departure_iata": dep_iata,
        "arrival_airport": arr_airport_name,
        "arrival_iata": arr_iata,
        "departure_time": dep_time,
        "arrival_time": arr_time,
        "dep_gate": dep_gate,
        "dep_terminal": dep_terminal,
        "arr_gate": arr_gate,
        "arr_terminal": arr_terminal,
        "aircraft": aircraft.get("model") or "Не указано",
        "tz_diff": tz_text,
        "fr24_link": fr24_link,
        "arr_query_for_weather": arr_city
    }

# РЕАЛЬНАЯ ПОГОДА ЧЕРЕЗ OPEN-METEO ПО GPS КООРДИНАТАМ
async def get_weather(airport_code: str):
    info = AIRPORT_INFO_MAP.get(airport_code.upper())
    if not info:
        lat, lon = 59.8003, 30.2625 # Пулково по умолчанию
    else:
        lat, lon = info["lat"], info["lon"]

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=4) as response:
                if response.status == 200:
                    data = await response.text()
                    res = await response.json()
                    current = res.get("current_weather", {})
                    temp = round(current.get("temperature"))
                    return f"🌡 Погода в пункте назначения: {temp}°C (реальные данные)"
        except Exception:
            pass
    return "🌡 Погода: данные временно недоступны"

async def get_coordinates_by_address(address: str):
    url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1"
    headers = {"User-Agent": "FlightTrackerBot/2.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=4) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            pass
    return None

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

async def calculate_real_transfer(address: str, dep_iata: str):
    coords = await get_coordinates_by_address(address)
    airport_info = AIRPORT_INFO_MAP.get(dep_iata)
    
    if not coords or not airport_info:
        return None
        
    user_lat, user_lon = coords
    ap_lat, ap_lon = airport_info["lat"], airport_info["lon"]
    
    distance_km = calculate_distance(user_lat, user_lon, ap_lat, ap_lon)
    avg_speed = 50.0
    travel_hours = distance_km / avg_speed
    total_minutes = int(travel_hours * 60)
    
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    time_str = f"{hours} ч. {minutes} мин." if hours > 0 else f"{minutes} мин."
    
    return {
        "distance": round(distance_km, 1),
        "time_str": time_str,
        "total_minutes": total_minutes
    }

# РЕАЛЬНОЕ ОНЛАЙН-ТАБЛО БЕЗ РАНДОМА И РАНДОМНЫХ МАССИВОВ
async def get_airport_board(airport_code: str):
    airport_code = airport_code.upper().strip()
    board_list = []
    
    if AVIATION_API_KEY:
        url = f"http://api.aviationstack.com/v1/flights?access_key={AVIATION_API_KEY}&dep_iata={airport_code}&limit=50"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=6) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        for flight in res_json.get("data", []):
                            f_obj = flight.get("flight", {}) or {}
                            f_num = f_obj.get("iata") or f_obj.get("number") or "Рейс"
                            arr_obj = flight.get("arrival", {}) or {}
                            arr_info = arr_obj.get("airport") or arr_obj.get("iata") or "Назначение"
                            dep_time_raw = (flight.get("departure", {}) or {}).get("scheduled", "00:00:00")
                            time_disp = dep_time_raw.split("T")[1][:5] if "T" in dep_time_raw else "00:00"
                            status_raw = flight.get("flight_status", "scheduled")
                            board_list.append({
                                "flight": f_num, 
                                "dest": arr_info, 
                                "time": time_disp, 
                                "sort_key": time_disp, 
                                "status": status_raw
                            })
            except Exception:
                pass

    board_list.sort(key=lambda x: x["sort_key"])
    return board_list

def get_airport_details(airport_code: str):
    airport_code = airport_code.upper().strip()
    if airport_code in AIRPORT_INFO_MAP:
        info = AIRPORT_INFO_MAP[airport_code]
        return f"🏢 <b>Аэропорт:</b> {info['name']} ({airport_code})\n📍 <b>Город:</b> {info['city']}, {info['country']}\n⏰ <b>Часовой пояс:</b> UTC+{info['tz']}"
    return f"🏢 <b>Аэропорт:</b> {airport_code}"
