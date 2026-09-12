import os
import aiohttp
from datetime import datetime, timezone, timedelta

AIRPORT_DATA = {
    "SVO": {"coords": (55.9726, 37.4146), "name": "Шереметьево (Москва)", "code": "s9600213", "city": "Москва"},
    "DME": {"coords": (55.4088, 37.9063), "name": "Домодедово (Москва)", "code": "s9600216", "city": "Москва"},
    "VKO": {"coords": (55.5915, 37.2615), "name": "Внуково (Москва)", "code": "s9600215", "city": "Москва"},
    "LED": {"coords": (59.8003, 30.2625), "name": "Пулково (Санкт-Петербург)", "code": "s9600370", "city": "Санкт-Петербург"},
    "OVB": {"coords": (55.0126, 82.6507), "name": "Толмачево (Новосибирск)", "code": "s9600366", "city": "Новосибирск"},
    "DXB": {"coords": (25.2532, 55.3657), "name": "Дубай", "code": "s9632080", "city": "Дубай"},
    "AYT": {"coords": (36.8987, 30.8005), "name": "Анталья", "code": "s9632093", "city": "Анталья"},
}

API_KEY = os.getenv("YANDEX_RASP_API_KEY")

async def get_flight_info(flight_number: str):
    raw_flight = flight_number.upper().replace(" ", "").replace("-", "")
    if not API_KEY:
        return _fallback_flight(raw_flight)

    today_str = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")
    url = f"https://api.rasp.yandex.net/v3.0/search/?apikey={API_KEY}&query={raw_flight}&date={today_str}&transport_types=plane"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    segments = data.get("segments", [])
                    if segments:
                        seg = segments[0]
                        thread = seg.get("thread", {})
                        
                        dep_station = seg.get("from", {}).get("title", "Аэропорт вылета")
                        dep_iata = seg.get("from", {}).get("code", "OVB")
                        arr_station = seg.get("to", {}).get("title", "Аэропорт назначения")
                        arr_iata = seg.get("to", {}).get("code", "SVO")
                        
                        dep_time_raw = seg.get("departure", "")
                        arr_time_raw = seg.get("arrival", "")
                        
                        dep_time = dep_time_raw.split("T")[1][:5] if "T" in dep_time_raw else "--:--"
                        arr_time = arr_time_raw.split("T")[1][:5] if "T" in arr_time_raw else "--:--"
                        
                        airline_data = thread.get("carrier", {})
                        airline_name = airline_data.get("title", "Авиакомпания")
                        
                        aircraft = thread.get("vehicle", "—")

                        return {
                            "flight": raw_flight,
                            "airline": airline_name,
                            "status": "Выполняется / По плану ✅",
                            "departure_airport": dep_station,
                            "departure_iata": dep_iata,
                            "arrival_airport": arr_station,
                            "arrival_iata": arr_iata,
                            "departure_time": dep_time,
                            "arrival_time": arr_time,
                            "dep_gate": "—",
                            "dep_terminal": "—",
                            "arr_gate": "—",
                            "arr_terminal": "—",
                            "tz_diff": "",
                            "aircraft": aircraft,
                            "fr24_link": f"https://www.flightradar24.com/data/flights/{raw_flight.lower()}",
                            "arr_query_for_weather": arr_station
                        }
        except Exception as e:
            print(f"Flight API Error: {e}")

    return _fallback_flight(raw_flight)

def _fallback_flight(raw_flight):
    return {
        "flight": raw_flight,
        "airline": "Авиакомпания",
        "status": "Отслеживается на Flightradar24 ✈️",
        "departure_airport": "Информация в табло",
        "departure_iata": "OVB",
        "arrival_airport": "Москва",
        "arrival_iata": "SVO",
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
    
    # Московское время (UTC+3), чтобы табло всегда совпадало с реальностью
    msk_time = datetime.now(timezone(timedelta(hours=3)))
    today_str = msk_time.strftime("%Y-%m-%d")
    now_time = msk_time.strftime("%H:%M")
    
    url = f"https://api.rasp.yandex.net/v3.0/schedule/?apikey={API_KEY}&station={station_code}&transport_types=plane&event=departure&date={today_str}"

    board_list = []
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=12) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    schedule = data.get("schedule", [])
                    
                    for item in schedule:
                        thread = item.get("thread", {})
                        f_num = thread.get("number") or item.get("number") or "Рейс"
                        
                        raw_dest = item.get("to", {}).get("title") or thread.get("title", "Пункт назначения")
                        dest = raw_dest.split(" — ")[-1] if " — " in raw_dest else raw_dest
                        
                        dep_time = item.get("departure") or item.get("time") or ""
                        time_str = "--:--"
                        if "T" in str(dep_time):
                            time_str = str(dep_time).split("T")[1][:5]
                        elif " " in str(dep_time):
                            time_str = str(dep_time).split(" ")[1][:5]
                        elif len(str(dep_time)) >= 5 and ":" in str(dep_time):
                            time_str = str(dep_time)[:5]

                        board_list.append({
                            "flight": str(f_num),
                            "dest": str(dest)[:20],
                            "time": time_str
                        })
        except Exception as e:
            print(f"Ошибка запроса к Яндекс.Расписаниям: {e}")

    if not board_list:
        return None

    # Показываем рейсы начиная с текущей минуты
    upcoming_flights = [f for f in board_list if f["time"] >= now_time]
    result = upcoming_flights if upcoming_flights else board_list[:30]
    
    return result[:30]

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
    airport_info = AIRPORT_DATA.get(airport_code, {"coords": (55.0126, 82.6507), "city": "Новосибирск"})
    a_lat, a_lon = airport_info["coords"]
    city_context = airport_info.get("city", "")

    query = f"{address}, {city_context}" if city_context and city_context.lower() not in address.lower() else address
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={query}&count=1"
    
    d_lat, d_lon = None, None
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(geo_url, timeout=5) as resp:
                if resp.status == 200:
                    results = (await resp.json()).get("results")
                    if results:
                        d_lat, d_lon = results[0]["latitude"], results[0]["longitude"]
        except Exception:
            pass

    if not d_lat:
        fallback_geo = f"https://geocoding-api.open-meteo.com/v1/search?name={address}&count=1"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(fallback_geo, timeout=5) as resp:
                    if resp.status == 200:
                        results = (await resp.json()).get("results")
                        if results:
                            d_lat, d_lon = results[0]["latitude"], results[0]["longitude"]
            except Exception:
                pass

    if not d_lat or not d_lon:
        return None

    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{d_lon},{d_lat};{a_lon},{a_lat}?overview=false"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(osrm_url, timeout=6) as resp:
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
