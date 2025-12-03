import asyncio
import logging
from datetime import datetime, timedelta
import random

from telethon import TelegramClient, events

from iron_business_hostess.config import Config
from iron_business_hostess.database import ReservationDB
from iron_business_hostess.llm_service import LLMService

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.WARNING)

class TelegramBot:
    def __init__(self):
        self.client = TelegramClient(Config.SESSION_NAME, Config.API_ID, Config.API_HASH)
        self.db = ReservationDB(Config.TIMEZONE, Config.SLOT_DURATION_MINUTES)
        self.llm_service = LLMService(Config.LLM_API_KEY, Config.LLM_BASE_URL, self.db)

        self.client.on(events.NewMessage)(self.handle_new_message)

    async def _apply_random_delay(self, response_text: str):
        base_delay = random.uniform(5, 20) # Random delay between 5 and 20 seconds
        length_delay = len(response_text) * 0.1 # 0.1 seconds per character
        total_delay = base_delay + length_delay
        print(f"Applying random delay of {total_delay:.2f} seconds...")
        await asyncio.sleep(total_delay)

    async def handle_new_message(self, event):
        sender = await event.get_sender()
        chat_id = event.chat_id
        message_text = event.text

        print(f"Received message from {sender.username or sender.id} in chat {chat_id}: {message_text}")

        # Call LLM service to parse request and potentially use tools
        parsed_data = await self.llm_service.parse_reservation_request(message_text)
        
        intent = parsed_data.get("intent")
        response_message = parsed_data.get("message", "Извините, я не совсем поняла ваш запрос.")

        if intent == "greeting":
            response = "Здравствуйте! Я хостесс ресторана \"Ромашка\". Могу помочь вам забронировать столик или ответить на вопросы."
        elif intent == "booked":
            response = (
                f"Отлично, {parsed_data.get('client_name')}! Ваш столик забронирован на "
                f"{parsed_data.get('datetime')} по московскому времени. "
                f"Номер телефона для связи: {parsed_data.get('phone_number')}. "
                f"Ждем вас! Хорошего дня!"
            )
        elif intent == "available":
            response = f"Столик на {parsed_data.get('datetime')} свободен. Могу забронировать его для вас?"
        elif intent == "unavailable":
            alternatives_str = "\n".join(parsed_data.get('alternatives', []))
            response = (
                f"К сожалению, столик на {parsed_data.get('datetime')} уже занят. "
                f"Могу предложить следующие свободные слоты:\n{alternatives_str}"
            )
        elif intent == "error":
            response = f"Произошла ошибка: {parsed_data.get('message', 'Неизвестная ошибка')}. Пожалуйста, попробуйте еще раз."
        else: # "other" intent or unexpected
            response = response_message # Use LLM's direct response for "other" or fallback

        await self._apply_random_delay(response)
        await event.respond(response)

    async def start(self):
        print("Starting Telegram Bot...")
        await self.client.start()
        print("Bot started. Listening for messages...")
        await self.client.run_until_disconnected()

    async def stop(self):
        print("Stopping Telegram Bot...")
        await self.client.disconnect()

