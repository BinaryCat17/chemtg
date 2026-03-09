import json
import config
import traceback
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BotCommand
from cachetools import TTLCache

from config import (
    TELEGRAM_TOKEN,
    whitelist_set,
    WHITELIST_FILE,
    load_whitelist,
    load_prompts,
)
from utils import (
    is_admin,
    is_whitelisted,
    log_prompt,
    format_for_telegram
)
from agent import RegistryAgent

# ================== БОТ И ДИСПЕТЧЕР ==================
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Глобальный словарь для сессий (каждый пользователь — своя история)
user_history = TTLCache(maxsize=1000, ttl=86400)

async def set_commands():
    """Установка команд в меню бота для всех пользователей"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="new", description="Новый вопрос (сбросить историю)"),
        BotCommand(command="listusers", description="Белый список (Admin)"),
        BotCommand(command="adduser", description="Добавить в список (Admin)"),
        BotCommand(command="removeuser", description="Удалить из списка (Admin)"),
        BotCommand(command="reload_prompt", description="Обновить промпты (Admin)"),
        BotCommand(command="debug", description="Проверить подключение"),
        BotCommand(command="help", description="Список команд"),
    ]
    # Устанавливаем команды для всех пользователей по умолчанию
    await bot.set_my_commands(commands, scope=types.BotCommandScopeDefault())


# ====================== КОМАНДЫ ======================
@dp.message(Command("start", "help"))
async def cmd_help(message: types.Message):
    # Принудительно обновляем команды при старте
    await set_commands()
    
    text = (
        "✅ <b>Бот-эксперт по Гостреестру запущен.</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/new — начать новый диалог (очистить историю)\n"
        "/help — показать это сообщение\n\n"
        "<b>Администрирование:</b>\n"
        "/listusers — список разрешенных пользователей\n"
        "/adduser @username — добавить пользователя\n"
        "/removeuser @username — удалить пользователя\n"
        "/reload_prompt — перезагрузить файлы промптов\n"
        "/debug — техническая информация"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("new"))
async def cmd_new(message: types.Message):
    if not await is_whitelisted(message.from_user):
        await message.answer("⛔ Доступ запрещён.")
        return
    if message.from_user.id in user_history:
        del user_history[message.from_user.id]
    await message.answer("🆕 История диалога сброшена. О чем хотите спросить?")


@dp.message(Command("debug"))
async def cmd_debug(message: types.Message):
    if not await is_whitelisted(message.from_user):
        await message.answer("⛔ Доступ запрещён.")
        return
    status = "✅ Подключено"
    await message.answer(f"🔍 <b>Debug Info:</b>\nСтатус: {status}\nUser ID: <code>{message.from_user.id}</code>\nAdmin: <code>{await is_admin(message.from_user.username)}</code>", parse_mode="HTML")


@dp.message(Command("adduser"))
async def cmd_adduser(message: types.Message):
    if not await is_admin(message.from_user.username):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/adduser @username</code>", parse_mode="HTML")
        return

    username = parts[1].strip().lower().replace("@", "")
    if not username:
        await message.answer("⚠️ Некорректный username.")
        return

    whitelist_set.add(username)
    try:
        WHITELIST_FILE.write_text(
            json.dumps(list(whitelist_set), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        await message.answer(f"✅ Пользователь <b>@{username}</b> добавлен в белый список.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении: {e}")


@dp.message(Command("removeuser"))
async def cmd_removeuser(message: types.Message):
    if not await is_admin(message.from_user.username):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/removeuser @username</code>", parse_mode="HTML")
        return

    username = parts[1].strip().lower().replace("@", "")
    if username in whitelist_set:
        whitelist_set.discard(username)
        try:
            WHITELIST_FILE.write_text(
                json.dumps(list(whitelist_set), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            await message.answer(f"✅ Пользователь <b>@{username}</b> удален из белого списка.", parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Ошибка при сохранении: {e}")
    else:
        await message.answer(f"❓ Пользователь @{username} не найден в списке.")


@dp.message(Command("listusers"))
async def cmd_listusers(message: types.Message):
    if not await is_admin(message.from_user.username):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    load_whitelist() # Перезагрузим на случай ручных правок файла
    users = "\n".join([f"• @{u}" for u in sorted(whitelist_set)]) or "<i>Список пуст</i>"
    await message.answer(f"📋 <b>Белый список ({len(whitelist_set)}):</b>\n{users}", parse_mode="HTML")


@dp.message(Command("reload_prompt"))
async def cmd_reload_prompt(message: types.Message):
    if not await is_admin(message.from_user.username):
        return
    load_prompts()
    await message.answer("✅ Промпты перезагружены из файлов!")


@dp.message()
async def handle_message(message: types.Message):
    if not await is_whitelisted(message.from_user):
        await message.answer("⛔ Доступ запрещён.")
        return

    wait_msg = await message.answer("⏳ Думаю...")
    user_id = message.from_user.id
    
    # 1. Формируем историю диалога внутри бота
    if user_id not in user_history:
        user_history[user_id] = []
        
    history = []
    for msg in user_history[user_id][-10:]:
        if msg.startswith("Пользователь: "):
            history.append({"role": "user", "content": msg.replace("Пользователь: ", "")})
        elif msg.startswith("Ассистент: "):
            history.append({"role": "assistant", "content": msg.replace("Ассистент: ", "")})

    # 2. Делаем запрос через агента
    try:
        # Используем username если есть, иначе user_id
        session_id = message.from_user.username or str(user_id)
        session_id = session_id.replace("@", "")
        
        # Инициализируем агента с ID сессии
        agent = RegistryAgent(session_id=session_id)
        
        response = await agent.process_message(message.text, history)
        
        # 3. Форматируем ответ для Telegram
        formatted_response = format_for_telegram(response)
        
        # 4. Сохраняем в историю
        user_history[user_id].append(f"Пользователь: {message.text}")
        user_history[user_id].append(f"Ассистент: {response}")

        # 5. Отправляем пользователю
        await wait_msg.edit_text(formatted_response[:4000], parse_mode="HTML")
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"❌ ERROR in handle_message:\n{error_trace}", file=sys.stderr, flush=True)
        
        error_text = f"❌ Произошла ошибка при обработке сообщения:\n<pre>{str(e)}</pre>\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
        try:
            await wait_msg.edit_text(error_text, parse_mode="HTML")
        except:
            await message.answer(error_text, parse_mode="HTML")
