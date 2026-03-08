import asyncio
from config import load_whitelist, load_prompts
from handlers import dp, bot, set_commands

async def main():
    print("🤖 Telegram-бот запущен (МОДУЛЬНАЯ ВЕРСИЯ)", flush=True)
    load_whitelist()
    load_prompts()
    await set_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    