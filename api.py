import aiohttp
import os

AVIATION_API_KEY = os.getenv("AVIATION_API_KEY", "")

AIRLINE_PREFIX_MAP = {
    "S7": "SBI",
    "SU": "AFL",
    "FV": "SDM",
    "U6": "SVR",
    "UT": "UTA",
    "DP": "PBD",
    "EK": "UAE",
    "TK": "THY",
    "FZ": "FDB"
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
                                flight = flights_list[0]
                                arr = flight.get("arrival", {}) or {}
                                dep = flight.get("departure", {}) or {}
                                airline = flight.get("airline", {}) or {}
                                aircraft = flight.get("aircraft", {}) or {}
                                
                                status_raw = flight.get("flight_status", "active")
                                status_map = {
                                    "active": "В ПОЛЕТЕ 🟢",
                                    "scheduled": "ПО РАСПИСАНИЮ ✈️",
                                    "landed": "ПРИБЫЛ 🛬",
                                    "cancelled": "ОТМЕНЕН ❌",
                                    "incident": "ЗАДЕРЖАН / ЧП ⚠️"
                                }
                                status_text = status_map.get(status_raw, status_raw.upper())

                                dep_time = dep.get("scheduled", "—")
                                if dep_time and "T" in dep_time:
                                    dep_time = dep_time.replace("T", " ")[:16]

                                arr_time = arr.get("scheduled", "—")
                                if arr_time and "T" in arr_time:
                                    arr_time = arr_time.replace("T", " ")[:16]

                                arr_city = arr.get("city") or arr.get("iata") or "Moscow"

                                return {
                                    "flight": raw_input,
                                    "airline": airline.get("name", "Регулярный рейс"),
                                    "status": status_text,
                                    "departure_airport": dep.get("airport", "Аэропорт отправления"),
                                    "arrival_airport": arr.get("airport", "Аэропорт назначения"),
                                    "departure_time": dep_time,
                                    "arrival_time": arr_time,
                                    "duration": "По расписанию",
                                    "gate": arr.get("gate") or "Уточняется",
                                    "terminal": arr.get("terminal") or "Главный",
                                    "aircraft": aircraft.get("model", "Коммерческий лайнер"),
                                    "arr_city_code": arr_city
                                }
                except Exception:
                    pass

    # Если ключ не задан или рейс не нашелся в API
    return None

async def get_airport_board(airport_code: str):
    airport_code = airport_code.upper().strip()
    
    if AVIATION_API_KEY:
        url = f"http://api.aviationstack.com/v1/flights?access_key={AVIATION_API_KEY}&dep_iata={airport_code}&limit=6"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=6) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        flights_data = res_json.get("data", [])
                        if flights_data:
                            board_list = []
                            for flight in flights_data:
                                flight_obj = flight.get("flight", {}) or {}
                                f_num = flight_obj.get("iata") or flight_obj.get("number") or "REIS"
                                
                                arr_obj = flight.get("arrival", {}) or {}
                                arr_info = arr_obj.get("airport") or arr_obj.get("iata") or "Назначение"
                                
                                dep_obj = flight.get("departure", {}) or {}
                                dep_time = dep_obj.get("scheduled", "—")
                                if dep_time and "T" in dep_time:
                                    dep_time = dep_time.split("T")[1][:5]
                                
                                status_raw = flight.get("flight_status", "scheduled")
                                status_map = {
                                    "active": "Летит 🟢",
                                    "scheduled": "По расписанию ✈️",
                                    "landed": "Посадка 🛬",
                                    "cancelled": "Отменен ❌"
                                }
                                status_text = status_map.get(status_raw, "Активен 🟢")
                                
                                board_list.append({
                                    "flight": f_num,
                                    "dest": arr_info,
                                    "time": dep_time,
                                    "status": status_text
                                })
                            return board_list
            except Exception:
                pass

    return []

async def get_weather(city_query: str):
    url = f"https://wttr.in/{city_query}?format=%C+%t"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=4) as response:
                if response.status == 200:
                    text = await response.text()
                    if "html" not in text.lower() and len(text.strip()) < 30:
                        return f"🌡 Погода в пункте прилета: {text.strip()}"
        except Exception:
            pass
        return "🌡 Погода: данные уточняются"
