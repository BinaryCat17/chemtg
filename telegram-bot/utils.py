import config
from config import ADMIN_USERNAME, whitelist_set, load_whitelist, log_prompt
from aiogram.types import User
import re
import html


def format_for_telegram(text: str) -> str:
    """
    Преобразует Markdown в HTML для Telegram.
    Безопасно обрабатывает жирный текст и таблицы.
    """
    if not text:
        return text

    # 0. Экранируем HTML, чтобы Telegram не ругался на случайные < или >
    text = html.escape(text)

    # 1. Жирный текст: заменяем **текст** на <b>текст</b>
    # Используем максимально простое и экранированное выражение
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    
    # 2. Парсинг таблиц в карточки
    lines = text.split('\n')
    out_lines = []
    in_table = False
    headers = []
    
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith('|') and line_stripped.endswith('|'):
            in_table = True
            cells = [c.strip() for c in line_stripped.strip('|').split('|')]
            
            # Пропускаем разделители таблиц
            if all(c.replace('-', '').replace(':', '').strip() == '' for c in cells):
                continue
            
            if not headers:
                # Очищаем заголовки от возможных тегов
                headers = [re.sub(r"&lt;[^&]+&gt;", "", c) for c in cells]
                continue
            
            out_lines.append("──────────────")
            for i, cell in enumerate(cells):
                header = headers[i] if i < len(headers) else f"Поле {i+1}"
                if cell: 
                    out_lines.append(f"▪️ <b>{header}:</b> {cell}")
        else:
            if in_table:
                in_table = False
                headers = []
                out_lines.append("──────────────\n")
            out_lines.append(line)
            
    if in_table:
        out_lines.append("──────────────")
        
    return "\n".join(out_lines)

async def is_admin(username: str) -> bool:
    if not username: return False
    return username.lower().replace("@", "") == ADMIN_USERNAME


async def is_whitelisted(user: User) -> bool:
    load_whitelist()
    if not user or not user.username:
        return False
    username_clean = user.username.lower().replace("@", "")
    return await is_admin(user.username) or username_clean in whitelist_set
