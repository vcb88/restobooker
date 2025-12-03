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
            "description": "Бронирует столик на указанную дату и время для клиента. Возвращает подтверждение бронирования или информацию о том, что слот занят.",
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
                },
                "required": ["date", "time", "client_name", "phone_number"],
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

    def _check_slot_availability(self, date: str, time: str) -> str:
        try:
            parsed_date = self._parse_date(date)
            parsed_time = self._parse_time(time)
            if not parsed_date or not parsed_time:
                return json.dumps({"status": "error", "message": "Некорректный формат даты или времени."})

            reservation_datetime = pytz.timezone(Config.TIMEZONE).localize(
                datetime.combine(parsed_date.date(), parsed_time.time())
            )

            if self.db.is_slot_available(reservation_datetime):
                return json.dumps({"status": "available", "datetime": str(reservation_datetime)})
            else:
                alternatives = self.db.get_alternative_slots(reservation_datetime)
                return json.dumps({"status": "unavailable", "alternatives": [str(alt) for alt in alternatives]})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _book_slot(self, date: str, time: str, client_name: str, phone_number: str) -> str:
        try:
            parsed_date = self._parse_date(date)
            parsed_time = self._parse_time(time)
            if not parsed_date or not parsed_time:
                return json.dumps({"status": "error", "message": "Некорректный формат даты или времени."})

            reservation_datetime = pytz.timezone(Config.TIMEZONE).localize(
                datetime.combine(parsed_date.date(), parsed_time.time())
            )

            if self.db.book_slot(reservation_datetime, client_name, phone_number):
                return json.dumps({"status": "booked", "datetime": str(reservation_datetime), "client_name": client_name, "phone_number": phone_number})
            else:
                return json.dumps({"status": "error", "message": "Слот уже занят или произошла ошибка при бронировании."})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    async def parse_reservation_request(self, text: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": f"""Ты - хостесс ресторана. Твоя задача - определить намерение клиента и извлечь необходимую информацию.
            
            Возможные намерения:
            - `greeting`: Если клиент просто здоровается, благодарит или прощается.
            - `booking_intent`: Если клиент хочет забронировать столик.
            - `other`: Во всех остальных случаях, когда намерение не относится к приветствию или бронированию. В таких случаях отвечай уклончиво, фокусируясь на своих навыках хостесс ресторана "Ромашка" и предлагая помощь в бронировании столика. Например, если спрашивают "Как дела?", ответь: "Дела отлично, я готова помочь забронировать лучшие столики в ресторане Ромашка!". Если спрашивают о погоде, ответь: "Я не владею этой информацией, но с удовольствием помогу забронировать столик в ресторане Ромашка."
            
            Если намерение `booking_intent`, извлеки следующую информацию: дату, время, имя клиента и номер телефона.
            Если какая-либо информация для бронирования отсутствует, укажи это.
            Дата может быть относительной (например, 'сегодня', 'завтра', 'послезавтра') или абсолютной (например, '25 октября', '25.10', '25.10.2025').
            Время должно быть в формате HH:MM.
            Номер телефона должен быть полным, включая код страны.
            Имя клиента - это имя человека, который бронирует столик.
            
            Верни информацию в формате JSON.
            
            Пример для `booking_intent` (если вся информация есть):
            {{"intent": "booking_intent", "date": "сегодня", "time": "19:00", "client_name": "Алексей", "phone_number": "+79123456789"}}
            
            Пример для `booking_intent` (если не хватает информации):
            {{"intent": "booking_intent", "date": "завтра", "time": "20:00", "client_name": null, "phone_number": null}}
            
            Пример для `greeting`:
            {{"intent": "greeting"}}
            
            Пример для `other`:
            {{"intent": "other"}}

            Информация о ресторане:
            1. График работы: ежедневно, с 8:00 до 24:00.
            2. Столики: есть в зале и на веранде.
            3. Парковка: есть возле ресторана.
            4. Дополнительные услуги: по выходным во второй половине дня играет живая музыка.
            5. Меню: большое количество блюд из кухонь разных народов мира, основной акцент на русской домашней кухне.
            
            Сообщение клиента: """{text}"""
            """}},
            {"role": "user", "content": text}
        ]

        # First LLM call: determine intent or tool call
        response = await self.client.chat.completions.create(
            model=Config.LLM_MODEL, # Use configurable model
            messages=messages,
            tools=self.TOOLS,
            tool_choice="auto",
            response_format={ "type": "json_object" } # Ensure JSON output for non-tool responses
        )
        
        response_message: ChatCompletionMessage = response.choices[0].message
        tool_calls: Optional[list[ChatCompletionMessageToolCall]] = response_message.tool_calls

        if tool_calls:
            # Step 2: call the tool
            available_functions = {
                "check_slot_availability": self._check_slot_availability,
                "book_slot": self._book_slot,
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
