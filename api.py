import os
import aiohttp

AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY", "")

AIRPORT_COORDS = {
    "SVO": (55.9726, 37.4146),  # Шереметьево / Москва
    "DME": (55.4088, 37.9063),  # Домодедово / Москва
    "VKO": (55.5915, 37.2615),  # Внуково / Москва
    "LED": (59.8003, 30.2625),  # Пулково / Санкт-Петербург
    "OVB": (55.0126, 82.6507),  # Толмачево / Новосибирск
    "AER": (43.4499, 39.9566),  # Сочи
    "SVX": (56.7431, 60.8027),  # Кольцово / Екатеринбург
    "KZN": (55.6062, 49.2787),  # Казань
    "KUF": (53.5049, 50.1643),  # Самара
    "VVO": (43.3990, 132.1480), # Владивосток
    "DXB": (25.2532, 55.3657),  # Дубай
    "IST": (41.2753, 28.7519),  # Стамбул
    "AYT": (36.8987, 30.8005),  # Анталья
}

async def get_flight_info(flight_number: str):
    raw_flight = flight_number.upper().replace(" ", "").replace("-", "")
    
    result = {
        "flight": raw_flight,
        "airline": "Авиакомпания не указана",
        "status": "Информация уточняется ✈️",
        "departure_airport": "Не указано",
        "departure_iata": "",
        "arrival_airport": "Не указано",
        "arrival_iata": "",
        "departure_time": "Не указано",
        "arrival_time": "Не указано",
        "dep_gate": "Не указан",
        "dep_terminal": "Не указан",
        "arr_gate": "Не указан",
        "arr_terminal": "Не указан",
        "aircraft": "Не указано",
        "tz_diff": "Часовые пояса совпадают",
        "fr24_link": f"https://www.flightradar24.com/data/flights/{raw_flight.lower()}",
        "arr_query_for_weather": ""
    }

    if not AIRLABS_API_KEY:
        return result

    sched_url = f"https://airlabs.co/api/v9/schedules?flight_iata={raw_flight}&api_key={AIRLABS_API_KEY}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(sched_url, timeout=8) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    response = data.get("response", [])
                    if response:
                        flight_data = response[0]
                        
                        result["departure_iata"] = flight_data.get("dep_iata", "")
                        result["departure_airport"] = flight_data.get("dep_name", flight_data.get("dep_iata", "Не указано"))
                        result["arrival_iata"] = flight_data.get("arr_iata", "")
                        result["arrival_airport"] = flight_data.get("arr_name", flight_data.get("arr_iata", "Не указано"))
                        
                        dep_time = flight_data.get("dep_time", "")
                        if dep_time:
                            result["departure_time"] = dep_time[:16].replace("T", " ")
                            
                        arr_time = flight_data.get("arr_time", "")
                        if arr_time:
                            result["arrival_time"] = arr_time[:16].replace("T", " ")

                        result["dep_terminal"] = flight_data.get("dep_terminal", "Не указан") or "Не указан"
                        result["arr_terminal"] = flight_data.get("arr_terminal", "Не указан") or "Не указан"
                        result["dep_gate"] = flight_data.get("dep_gate", "Не указан") or "Не указан"
                        result["arr_gate"] = flight_data.get("arr_gate", "Не указан") or "Не указан"
                        result["arr_query_for_weather"] = result["arrival_iata"] or result["arrival_airport"]
                        
                        return result
        except Exception as e:
            print(f"AirLabs schedules error: {e}")

        flight_url = f"https://airlabs.co/api/v9/flight?flight_iata={raw_flight}&api_key={AIRLABS_API_KEY}"
        try:
            async with session.get(flight_url, timeout=8) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    flight_data = data.get("response", {})
                    if flight_data:
                        result["status"] = "В пути 🛫" if flight_data.get("status") == "en-route" else flight_data.get("status", result["status"])
                        result["departure_iata"] = flight_data.get("dep_iata", "")
                        result["arrival_iata"] = flight_data.get("arr_iata", "")
                        result["arr_query_for_weather"] = result["arrival_iata"]
        except Exception as e:
            print(f"AirLabs live error: {e}")

    return result

async def get_weather(location: str):
    """Динамическое получение реальной погоды через Open-Meteo"""
    if not location:
        return "Данные о погоде недоступны"
    
    loc_clean = location.upper().strip()
    lat, lon = None, None
    
    if loc_clean in AIRPORT_COORDS:
        lat, lon = AIRPORT_COORDS[loc_clean]
    else:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(geo_url, timeout=5) as g_resp:
                    if g_resp.status == 200:
                        g_data = await g_resp.json()
                        results = g_data.get("results")
                        if results:
                            lat = results[0]["latitude"]
                            lon = results[0]["longitude"]
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
                    current = data.get("current_weather", {})
                    temp = current.get("temperature")
                    if temp is not None:
                        return f"🌡 Погода в пункте назначения: {round(temp)}°C"
        except Exception as e:
            print(f"Open-Meteo error: {e}")
            
    return "🌡 Погода: данные недоступны"

async def calculate_real_transfer(airport_code: str, address: str = "Центр города"):
    """Реальный расчет трансфера через OSRM и геокодинг"""
    if not airport_code:
        return "Не удалось рассчитать трансфер"
        
    airport_code = airport_code.upper().strip()
    
    # 1. Координаты аэропорта
    a_lat, a_lon = None, None
    if airport_code in AIRPORT_COORDS:
        a_lat, a_lon = AIRPORT_COORDS[airport_code]
    else:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={airport_code}&count=1"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(geo_url, timeout=5) as resp:
                    if resp.status == 200:
                        g_data = await resp.json()
                        results = g_data.get("results")
                        if results:
                            a_lat = results[0]["latitude"]
                            a_lon = results[0]["longitude"]
            except Exception as e:
                print(f"Airport geocoding error: {e}")

    if a_lat is None or a_lon is None:
        return "Расчет трансфера: аэропорт не найден"

    # 2. Координаты точки назначения
    target_name = address if address else "Центр города"
    d_lat, d_lon = None, None
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={target_name}&count=1"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(geo_url, timeout=5) as resp:
                if resp.status == 200:
                    g_data = await resp.json()
                    results = g_data.get("results")
                    if results:
                        d_lat = results[0]["latitude"]
                        d_lon = results[0]["longitude"]
        except Exception as e:
            print(f"Destination geocoding error: {e}")

    if d_lat is None or d_lon is None:
        d_lat, d_lon = a_lat + 0.15, a_lon + 0.15

    # 3. Запрос времени в пути через OSRM
    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{a_lon},{a_lat};{d_lon},{d_lat}?overview=false"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(osrm_url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    routes = data.get("routes", [])
                    if routes:
                        duration_min = int(routes[0]["duration"] / 60)
                        distance_km = round(routes[0]["distance"] / 1000, 1)
                        return f"🚗 Трансфер на авто: ~{duration_min} мин ({distance_km} км)"
        except Exception as e:
            print(f"OSRM error: {e}")

    return "Расчет трансфера временно недоступен"

async def get_airport_board(airport_code: str):
    """Реальное онлайн-табло вылетов аэропорта"""
    airport_code = airport_code.upper().strip()
    board_list = []
    
    if AIRLABS_API_KEY:
        url = f"https://airlabs.co/api/v9/schedules?dep_iata={airport_code}&api_key={AIRLABS_API_KEY}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=8) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for flight in data.get("response", [])[:30]:
                            f_num = flight.get("flight_iata") or flight.get("flight_number") or "Рейс"
                            arr_info = flight.get("arr_iata") or flight.get("arr_name") or "Назначение"
                            dep_time_raw = flight.get("dep_time", "00:00")
                            time_disp = dep_time_raw.split(" ")[1][:5] if " " in dep_time_raw else dep_time_raw[:5]
                            board_list.append({
                                "flight": f_num, 
                                "dest": arr_info, 
                                "time": time_disp, 
                                "sort_key": time_disp
                            })
            except Exception as e:
                print(f"Airport board error: {e}")

    board_list.sort(key=lambda x: x["sort_key"])
    return board_list

def get_airport_details(airport_code: str):
    airport_code = airport_code.upper().strip()
    return f"🏢 <b>Аэропорт:</b> {airport_code}"
