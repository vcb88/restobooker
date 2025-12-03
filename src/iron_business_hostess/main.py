import asyncio
from iron_business_hostess.telegram_bot import TelegramBot

async def main():
    bot = TelegramBot()
    await bot.start()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
