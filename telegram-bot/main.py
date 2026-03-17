import asyncio
from config import load_whitelist, load_prompts
from handlers import dp, bot, set_commands

async def main():
    print("🤖 Telegram-бот запущен (МОДУЛЬНАЯ ВЕРСИЯ)", flush=True)
    load_whitelist()
    load_prompts()
    await set_commands()
    # Запуск бота с оптимизацией
    await dp.start_polling(bot, skip_updates=True, polling_timeout=20)

if __name__ == "__main__":
    asyncio.run(main())
    