import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import pytz
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from iron_business_hostess.config import Config

class LLMService:
    def __init__(self, api_key: str, base_url: str, db: Any):
        self.api_key = api_key
        self.base_url = base_url
        self.db = db
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_slot_availability",
            "description": "Проверяет доступность столика на указанную дату и время. Возвращает информацию о доступности и, если слот занят, предлагает альтернативные варианты.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Дата бронирования в формате 'YYYY-MM-DD' или относительная дата (например, 'сегодня', 'завтра').",
                    },
                    "time": {
                        "type": "string",
                        "description": "Время бронирования в формате 'HH:MM'.",
                    },
                },
                "required": ["date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_slot",
            "description": "Бронирует столик на указанную дату и время для клиента. Возвращает подтверждение бронирования или информацию о том, что подходящих столиков нет.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Дата бронирования в формате 'YYYY-MM-DD' или относительная дата (например, 'сегодня', 'завтра').",
                    },
                    "time": {
                        "type": "string",
                        "description": "Время бронирования в формате 'HH:MM'.",
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Имя клиента, который бронирует столик.",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Номер телефона клиента для связи.",
                    },
                    "guests_count": {
                        "type": "integer",
                        "description": "Количество гостей (по умолчанию 2).",
                    },
                },
                "required": ["date", "time", "client_name", "phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reservation",
            "description": "Отменяет существующее бронирование по номеру телефона клиента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Номер телефона клиента, чью бронь нужно отменить.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Опционально: дата отменяемой брони.",
                    },
                },
                "required": ["phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "change_reservation",
            "description": "Переносит существующее бронирование на новое время/дату по номеру телефона клиента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Номер телефона клиента.",
                    },
                    "new_date": {
                        "type": "string",
                        "description": "Новая дата бронирования.",
                    },
                    "new_time": {
                        "type": "string",
                        "description": "Новое время бронирования.",
                    },
                    "old_date": {
                        "type": "string",
                        "description": "Опционально: текущая дата бронирования (для уточнения).",
                    },
                },
                "required": ["phone_number", "new_date", "new_time"],
            },
        },
    },
]

    def _get_mock_llm_response(self, text: str) -> str:
        # This is a mock LLM response for testing purposes
        text_lower = text.lower()
        if "забронировать" in text_lower and "сегодня" in text_lower and "18:00" in text_lower and "иван" in text_lower and "1234567890" in text_lower:
            return json.dumps({"intent": "booking_intent", "date": "today", "time": "18:00", "client_name": "Иван", "phone_number": "+791234567890"})
        elif "забронировать" in text_lower and "завтра" in text_lower and "20:30" in text_lower and "мария" in text_lower and "0987654321" in text_lower:
            return json.dumps({"intent": "booking_intent", "date": "tomorrow", "time": "20:30", "client_name": "Мария", "phone_number": "+790987654321"})
        elif "привет" in text_lower or "здравствуйте" in text_lower or "спасибо" in text_lower or "до свидания" in text_lower:
            return json.dumps({"intent": "greeting"})
        elif "как дела" in text_lower or "что нового" in text_lower:
            return json.dumps({"intent": "other"})
        return json.dumps({"intent": "other"})

    def _check_slot_availability(self, date: str, time: str, guests_count: int = 2) -> str:
        try:
            parsed_date = self._parse_date(date)
            parsed_time = self._parse_time(time)
            if not parsed_date or not parsed_time:
                return json.dumps({"status": "error", "message": "Некорректный формат даты или времени."})

            reservation_datetime = pytz.timezone(Config.TIMEZONE).localize(
                datetime.combine(parsed_date.date(), parsed_time.time())
            )

            table_id = self.db.find_available_table(reservation_datetime, guests_count)
            if table_id:
                return json.dumps({"status": "available", "datetime": str(reservation_datetime), "guests_count": guests_count})
            else:
                alternatives = self.db.get_alternative_slots(reservation_datetime, guests_count)
                return json.dumps({"status": "unavailable", "alternatives": [str(alt) for alt in alternatives]})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _book_slot(self, date: str, time: str, client_name: str, phone_number: str, guests_count: int = 2) -> str:
        try:
            parsed_date = self._parse_date(date)
            parsed_time = self._parse_time(time)
            if not parsed_date or not parsed_time:
                return json.dumps({"status": "error", "message": "Некорректный формат даты или времени."})

            reservation_datetime = pytz.timezone(Config.TIMEZONE).localize(
                datetime.combine(parsed_date.date(), parsed_time.time())
            )

            result = self.db.book_slot(reservation_datetime, client_name, phone_number, guests_count)
            if result:
                return json.dumps({
                    "status": "booked", 
                    "datetime": str(result["datetime"]), 
                    "client_name": client_name, 
                    "phone_number": phone_number,
                    "table_name": result["table_name"],
                    "zone": result["zone"],
                    "guests_count": guests_count
                })
            else:
                return json.dumps({"status": "error", "message": "К сожалению, подходящих свободных столиков на это время нет."})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _cancel_reservation(self, phone_number: str, date: Optional[str] = None) -> str:
        try:
            parsed_date = self._parse_date(date) if date else None
            success = self.db.cancel_reservation(phone_number, parsed_date)
            if success:
                return json.dumps({"status": "cancelled", "phone_number": phone_number})
            else:
                return json.dumps({"status": "error", "message": "Бронирование не найдено."})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _change_reservation(self, phone_number: str, new_date: str, new_time: str, old_date: Optional[str] = None) -> str:
        try:
            parsed_new_date = self._parse_date(new_date)
            parsed_new_time = self._parse_time(new_time)
            parsed_old_date = self._parse_date(old_date) if old_date else None
            
            if not parsed_new_date or not parsed_new_time:
                return json.dumps({"status": "error", "message": "Некорректный формат новой даты или времени."})

            new_dt = pytz.timezone(Config.TIMEZONE).localize(
                datetime.combine(parsed_new_date.date(), parsed_new_time.time())
            )

            result = self.db.update_reservation_time(phone_number, parsed_old_date, new_dt)
            if result:
                return json.dumps({
                    "status": "changed", 
                    "datetime": str(result["datetime"]), 
                    "phone_number": phone_number,
                    "table_name": result["table_name"],
                    "zone": result["zone"]
                })
            else:
                return json.dumps({"status": "error", "message": "Бронирование не найдено или новое время уже занято."})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    async def parse_reservation_request(self, text: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": f"""Ты - хостесс ресторана. Твоя задача - определить намерение клиента и извлечь необходимую информацию.
            
            Возможные намерения:
            - `greeting`: Если клиент просто здоровается, благодарит или прощается.
            - `booking_intent`: Если клиент хочет забронировать столик.
            - `cancel_intent`: Если клиент хочет отменить бронирование.
            - `change_intent`: Если клиент хочет перенести или изменить бронирование на другое время.
            - `other`: Во всех остальных случаях.
            
            Если намерение `booking_intent`, извлеки: дату, время, имя клиента, номер телефона и КОЛИЧЕСТВО ГОСТЕЙ (guests_count, по умолчанию 2).
            Если намерение `cancel_intent`, извлеки: номер телефона и (опционально) дату.
            Если намерение `change_intent`, извлеки: номер телефона, новую дату (new_date) и новое время (new_time).
...
            Информация о ресторане:
            1. График работы: ежедневно, с 8:00 до 24:00.
            2. Столики: есть в зале и на веранде. Всего 5 столов разной вместимости (от 2 до 8 человек).
            3. Парковка: есть возле ресторана.
...
        if tool_calls:
            # Step 2: call the tool
            available_functions = {
                "check_slot_availability": self._check_slot_availability,
                "book_slot": self._book_slot,
                "cancel_reservation": self._cancel_reservation,
                "change_reservation": self._change_reservation,
            }
            
            # Only one tool call is expected for simplicity
            tool_call = tool_calls[0]
            function_name = tool_call.function.name
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments)
            
            function_response = function_to_call(**function_args)
            
            # Step 3: send tool output back to LLM
            messages.append(response_message)
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )
            
            second_response = await self.client.chat.completions.create(
                model=Config.LLM_MODEL, # Use configurable model
                messages=messages,
                response_format={ "type": "json_object" } # Ensure JSON output
            )
            llm_output = second_response.choices[0].message.content
        else:
            llm_output = response_message.content

        try:
            parsed_data = json.loads(llm_output)
            return parsed_data
        except json.JSONDecodeError:
            print(f"Error decoding LLM response: {llm_output}")
            return {"intent": "other", "message": llm_output} # Return raw output if not JSON

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        today = datetime.now(pytz.timezone(Config.TIMEZONE)).date()
        if date_str.lower() == "сегодня":
            return datetime.combine(today, datetime.min.time())
        elif date_str.lower() == "завтра":
            return datetime.combine(today + timedelta(days=1), datetime.min.time())
        elif date_str.lower() == "послезавтра":
            return datetime.combine(today + timedelta(days=2), datetime.min.time())
        
        # Try to parse absolute date formats (e.g., '25 октября', '25.10', '25.10.2025')
        # This part can be more robust, but for now, a simple approach.
        try:
            # '25 октября'
            match = re.match(r"(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)", date_str, re.IGNORECASE)
            if match:
                day = int(match.group(1))
                month_name = match.group(2).lower()
                month_map = {
                    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
                    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
                }
                month = month_map.get(month_name)
                if month:
                    year = today.year
                    # If the month has already passed this year, assume next year
                    if month < today.month or (month == today.month and day < today.day):
                        year += 1
                    return datetime(year, month, day)
            
            # '25.10' or '25.10.2025'
            for fmt in ["%d.%m.%Y", "%d.%m"]:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    if fmt == "%d.%m": # If year is not provided, assume current year
                        parsed_date = parsed_date.replace(year=today.year)
                        # If the date has already passed this year, assume next year
                        if parsed_date.date() < today:
                            parsed_date = parsed_date.replace(year=today.year + 1)
                    return parsed_date
                except ValueError:
                    continue
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
            
        return None

    def _parse_time(self, time_str: str) -> Optional[datetime]:
        try:
            return datetime.strptime(time_str, "%H:%M")
        except ValueError:
            return None

    def extract_reservation_details(self, text: str) -> Dict[str, Any]:
        parsed_llm_data = self.parse_reservation_request(text)
        
        intent = parsed_llm_data.get("intent", "other")
        
        if intent == "greeting":
            return {"intent": "greeting"}

        if intent != "booking_intent":
            return {"intent": intent}

        date_str = parsed_llm_data.get("date")
        time_str = parsed_llm_data.get("time")
        client_name = parsed_llm_data.get("client_name")
        phone_number = parsed_llm_data.get("phone_number")

        reservation_datetime: Optional[datetime] = None
        if date_str and time_str:
            parsed_date = self._parse_date(date_str)
            parsed_time = self._parse_time(time_str)
            if parsed_date and parsed_time:
                reservation_datetime = pytz.timezone(Config.TIMEZONE).localize(
                    datetime.combine(parsed_date.date(), parsed_time.time())
                )

        return {
            "intent": intent,
            "datetime": reservation_datetime,
            "client_name": client_name,
            "phone_number": phone_number,
            "raw_date": date_str,
            "raw_time": time_str
        }
