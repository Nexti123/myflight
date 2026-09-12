import os
import aiohttp

AIRPORT_DATA = {
    "SVO": {"coords": (55.9726, 37.4146), "name": "Шереметьево (Москва)", "code": "s9600213"},
    "DME": {"coords": (55.4088, 37.9063), "name": "Домодедово (Москва)", "code": "s9600216"},
    "VKO": {"coords": (55.5915, 37.2615), "name": "Внуково (Москва)", "code": "s9600215"},
    "LED": {"coords": (59.8003, 30.2625), "name": "Пулково (Санкт-Петербург)", "code": "s9600370"},
    "OVB": {"coords": (55.0126, 82.6507), "name": "Толмачево (Новосибирск)", "code": "s9600366"},
    "DXB": {"coords": (25.2532, 55.3657), "name": "Дубай", "code": "s9632080"},
    "AYT": {"coords": (36.8987, 30.8005), "name": "Анталья", "code": "s9632093"},
}

API_KEY = os.getenv("YANDEX_RASP_API_KEY")

async def get_flight_info(flight_number: str):
    raw_flight = flight_number.upper().replace(" ", "").replace("-", "")
    return {
        "flight": raw_flight,
        "airline": "Авиакомпания",
        "status": "Отслеживается на Flightradar24 ✈️",
        "departure_airport": "Информация в табло",
        "departure_iata": "OVB",
        "arrival_airport": "Информация в табло",
        "arrival_iata": "DME",
        "departure_time": "--:--",
        "arrival_time": "--:--",
        "dep_gate": "—",
        "dep_terminal": "—",
        "arr_gate": "—",
        "arr_terminal": "—",
        "tz_diff": "",
        "aircraft": "—",
        "fr24_link": f"https://www.flightradar24.com/data/flights/{raw_flight.lower()}",
        "arr_query_for_weather": "Москва"
    }

async def get_airport_board(airport_code: str):
    code = airport_code.upper().strip()
    
    if not API_KEY:
        print("YANDEX_RASP_API_KEY не установлен!")
        return None

    station_code = AIRPORT_DATA.get(code, {}).get("code", code)
    url = f"https://api.rasp.yandex.net/v3.0/schedule/?apikey={API_KEY}&station={station_code}&transport_types=plane&event=departure"

    board_list = []
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    schedule = data.get("schedule", [])
                    for item in schedule[:20]:
                        thread = item.get("thread", {})
                        f_num = thread.get("number") or "Рейс"
                        
                        # Достаем город назначения
                        dest = item.get("to", {}).get("title") or thread.get("title", "Пункт назначения")
                        
                        # Достаем время HH:MM без мусора от ISO-формата
                        time_raw = item.get("departure", "")
                        time_str = "--:--"
                        if time_raw and "T" in time_raw:
                            time_str = time_raw.split("T")[1][:5]

                        board_list.append({
                            "flight": str(f_num),
                            "dest": str(dest)[:20],
                            "time": time_str
                        })
        except Exception as e:
            print(f"Ошибка запроса к Яндекс.Расписаниям: {e}")

    return board_list if board_list else None

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
        return "🌡 Погода: координаты не найдены"

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
