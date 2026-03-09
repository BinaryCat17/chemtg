import json
import config
import traceback
import sys
import asyncio
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
    commands_user = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="new", description="Новый вопрос (сбросить историю)"),
        BotCommand(command="help", description="Список команд"),
    ]
    commands_admin = commands_user + [
        BotCommand(command="listusers", description="Белый список (Admin)"),
        BotCommand(command="adduser", description="Добавить в список (Admin)"),
        BotCommand(command="removeuser", description="Удалить из списка (Admin)"),
        BotCommand(command="reload_prompt", description="Обновить промпты (Admin)"),
        BotCommand(command="debug", description="Проверить подключение"),
        BotCommand(command="update_info", description="Статус реестра (Admin)"),
        BotCommand(command="index_popularity", description="Индексировать популярность (Admin)"),
        BotCommand(command="top_popularity", description="Топ-30 индекса (Admin)"),
    ]
    # Устанавливаем команды для всех пользователей по умолчанию
    await bot.set_my_commands(commands_user, scope=types.BotCommandScopeDefault())

    # Устанавливаем админские команды, если задан ADMIN_ID
    if config.ADMIN_ID:
        try:
            await bot.set_my_commands(commands_admin, scope=types.BotCommandScopeChat(chat_id=config.ADMIN_ID))
        except Exception as e:
            print(f"[WARNING] Не удалось установить команды для администратора: {e}")


# ====================== КОМАНДЫ ======================
@dp.message(Command("start", "help"))
async def cmd_help(message: types.Message):
    # Принудительно обновляем команды при старте
    await set_commands()

    is_user_admin = await is_admin(message.from_user.id)
    has_access = await is_whitelisted(message.from_user)

    if not has_access:
        text = (
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Я — бот-эксперт по Государственному реестру пестицидов и агрохимикатов.\n"
            "К сожалению, сейчас бот находится в закрытом режиме тестирования, "
            "и ваш аккаунт не добавлен в белый список.\n\n"
            f"Ваш ID для запроса доступа: <code>{message.from_user.id}</code>"
        )
        await message.answer(text, parse_mode="HTML")
        return

    text = (
        "🌾 <b>Добро пожаловать в бот-эксперт по Гостреестру!</b>\n\n"
        "Я помогу вам найти информацию о пестицидах, агрохимикатах, проверить действующие вещества, нормы расхода и регламенты применения.\n\n"
        "<b>Основные команды:</b>\n"
        "/new — начать новый диалог (очистить историю)\n"
        "/help — показать это сообщение\n\n"
        "<i>Просто напишите мне название препарата, действующего вещества или ваш вопрос!</i>"
    )

    if is_user_admin:
        text += (
            "\n\n🛠 <b>Администрирование:</b>\n"
            "/listusers — список разрешенных ID\n"
            "/adduser ID — добавить ID пользователя\n"
            "/removeuser ID — удалить ID пользователя\n"
            "/reload_prompt — перезагрузить файлы промптов\n"
            "/update_info — статус базы данных\n"
            "/index_popularity — запустить индексацию популярности\n"
            "/top_popularity — посмотреть Топ-30 индекса\n"
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
    await message.answer(f"🔍 <b>Debug Info:</b>\nСтатус: {status}\nUser ID: <code>{message.from_user.id}</code>\nAdmin: <code>{await is_admin(message.from_user.id)}</code>", parse_mode="HTML")


@dp.message(Command("adduser"))
async def cmd_adduser(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/adduser USER_ID</code>", parse_mode="HTML")
        return

    user_id = parts[1].strip()
    if not user_id.isdigit():
        await message.answer("⚠️ USER_ID должен быть числом.")
        return

    whitelist_set.add(user_id)
    try:
        WHITELIST_FILE.write_text(
            json.dumps(list(whitelist_set), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        await message.answer(f"✅ ID <code>{user_id}</code> добавлен в белый список.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении: {e}")


@dp.message(Command("removeuser"))
async def cmd_removeuser(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/removeuser USER_ID</code>", parse_mode="HTML")
        return

    user_id = parts[1].strip()
    if user_id in whitelist_set:
        whitelist_set.discard(user_id)
        try:
            WHITELIST_FILE.write_text(
                json.dumps(list(whitelist_set), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            await message.answer(f"✅ ID <code>{user_id}</code> удален из белого списка.", parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Ошибка при сохранении: {e}")
    else:
        await message.answer(f"❓ ID {user_id} не найден в списке.")


@dp.message(Command("listusers"))
async def cmd_listusers(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    load_whitelist()
    users = "\n".join([f"• <code>{u}</code>" for u in sorted(whitelist_set)]) or "<i>Список пуст</i>"
    await message.answer(f"📋 <b>Белый список (ID):</b>\n{users}", parse_mode="HTML")


@dp.message(Command("reload_prompt"))
async def cmd_reload_prompt(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    load_prompts()
    await message.answer("✅ Промпты перезагружены из файлов!")


@dp.message(Command("update_info"))
async def cmd_update_info(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    from database import Database
    db = Database()
    try:
        query = "SELECT MAX(imported_at) as last_update, COUNT(*) as total FROM reestr.pestitsidy;"
        res = db.execute_query(query)
        last_date = res[0]['last_update'].strftime("%d.%m.%Y %H:%M") if res[0]['last_update'] else "Нет данных"
        total = res[0]['total']
        await message.answer(f"📊 <b>Статус реестра:</b>\nВсего препаратов: <code>{total}</code>\nПоследнее обновление: <code>{last_date}</code>\n\n🕒 Следующее автоматическое обновление: <b>сегодня в 00:00</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("index_popularity"))
async def cmd_index_popularity(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    from utils import index_all_products_popularity
    # Запускаем в фоне
    asyncio.create_task(index_all_products_popularity(bot, message.chat.id))
    await message.answer("🚀 Задача индексации запущена в фоновом режиме. Я буду уведомлять вас о прогрессе.")


@dp.message(Command("top_popularity"))
async def cmd_top_popularity(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    from database import Database
    db = Database()
    try:
        query = "SELECT naimenovanie, score FROM reestr.product_popularity ORDER BY score DESC LIMIT 30;"
        res = db.execute_query(query)
        if not res:
            await message.answer("ℹ️ Таблица популярности пуста. Запустите /index_popularity.")
            return
            
        text = "🏆 <b>Топ-30 популярных препаратов:</b>\n\n"
        for i, row in enumerate(res, 1):
            text += f"{i}. <b>{row['naimenovanie']}</b> — индекс <code>{row['score']}</code>\n"
        
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message()
async def handle_message(message: types.Message):
    if not await is_whitelisted(message.from_user):
        await message.answer("⛔ Доступ запрещён.")
        return

    user_id = message.from_user.id
    
    # 1. Инициализируем историю, если её нет
    if user_id not in user_history:
        user_history[user_id] = []
    
    # 2. Считаем количество пар Вопрос-Ответ (каждая пара - это 2 записи в user_history)
    msg_count = len(user_history[user_id]) // 2
    
    # 3. Реализуем автоматическую очистку на 15-м сообщении
    if msg_count >= 15:
        user_history[user_id] = []
        msg_count = 0
        await message.answer("🔄 <b>Автоматическая очистка:</b> История диалога сброшена из-за превышения лимита (15 сообщений).")

    wait_msg = await message.answer("⏳ Думаю...")
        
    history = []
    # Берем последние 10 записей для контекста LLM
    for msg in user_history[user_id][-10:]:
        if msg.startswith("Пользователь: "):
            history.append({"role": "user", "content": msg.replace("Пользователь: ", "")})
        elif msg.startswith("Ассистент: "):
            history.append({"role": "assistant", "content": msg.replace("Ассистент: ", "")})

    # 4. Делаем запрос через агента
    try:
        session_id = str(user_id)
        agent = RegistryAgent(session_id=session_id)
        response = await agent.process_message(message.text, history)
        
        # 5. Форматируем ответ
        formatted_response = format_for_telegram(response)
        
        # 6. Добавляем системные напоминания в конец сообщения
        # Обновляем счетчик после текущего сообщения
        current_count = msg_count + 1
        reminder = ""
        
        if current_count >= 10:
            reminder = "\n\n⚠️ <b>Внимание:</b> История перегружена. На 15-м сообщении она будет очищена автоматически."
        elif current_count >= 5:
            reminder = "\n\n💡 <b>Совет:</b> Используйте /new, чтобы сбросить контекст и улучшить качество ответов."
            
        final_text = f"{formatted_response[:3800]}{reminder}"

        # 7. Сохраняем в историю
        user_history[user_id].append(f"Пользователь: {message.text}")
        user_history[user_id].append(f"Ассистент: {response}")

        # 8. Отправляем пользователю
        await wait_msg.edit_text(final_text, parse_mode="HTML")
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"❌ ERROR in handle_message:\n{error_trace}", file=sys.stderr, flush=True)
        
        error_text = f"❌ Произошла ошибка при обработке сообщения:\n<pre>{str(e)}</pre>\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
        try:
            await wait_msg.edit_text(error_text, parse_mode="HTML")
        except:
            await message.answer(error_text, parse_mode="HTML")
