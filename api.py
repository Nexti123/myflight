import os
import aiohttp

AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY", "")

async def get_flight_info(flight_number: str):
    # Очищаем номер рейса (например, "S7-2514" -> "S72514")
    raw_flight = flight_number.upper().replace(" ", "").replace("-", "")
    
    result = {
        "flight": raw_flight,
        "airline": "S7 Airlines" if raw_flight.startswith("S7") else ("Аэрофлот" if raw_flight.startswith("SU") else "Авиакомпания"),
        "status": "Запланирован ✈️",
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
        "aircraft": "Airbus A320 / Boeing 737",
        "tz_diff": "Часовые пояса совпадают",
        "fr24_link": f"https://www.flightradar24.com/data/flights/{raw_flight.lower()}",
        "arr_query_for_weather": ""
    }

    if not AIRLABS_API_KEY:
        return result

    # 1. Сначала ищем в расписании (подойдет для будущих/невылетевших рейсов)
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
                        
                        # Если нашли рейс в расписании, отдаем результат
                        return result
        except Exception as e:
            print(f"AirLabs schedules error: {e}")

        # 2. Если в расписании не нашли, пробуем эндпоинт активных рейсов (онлайн)
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
