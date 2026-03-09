import config
from config import whitelist_set, load_whitelist, log_prompt
from aiogram.types import User
import re
import html


def format_for_telegram(text: str) -> str:
    """
    Преобразует Markdown в безопасный HTML для Telegram.
    Поддерживает жирный текст, курсив, моноширинный шрифт и списки.
    """
    if not text:
        return text

    # 1. Сначала очищаем текст от возможных "грязных" тегов, которые мог прислать агент (кроме разрешенных)
    # Но для безопасности мы сначала экранируем ВСЁ, а потом восстановим нужные теги
    text = html.escape(text)

    # 2. Восстанавливаем теги, которые МЫ РАЗРЕШИЛИ агенту использовать в промпте
    # (они уже экранированы как &lt;b&gt;, &lt;code&gt; и т.д.)
    text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    text = text.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    text = text.replace("&lt;pre&gt;", "<pre>").replace("&lt;/pre&gt;", "</pre>")

    # 3. Обработка Markdown синтаксиса (на случай, если агент его пришлет вместо HTML)
    
    # Жирный: **text** -> <b>text</b>
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    
    # Курсив: __text__ или *text* -> <i>text</i>
    text = re.sub(r"__(.*?)__", r"<i>\1</i>", text)
    # Осторожно с одиночными звездочками, они часто бывают в формулах или списках
    # Используем только если вокруг текста есть пробелы или начало строки
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", text)

    # Моноширинный (inline): `text` -> <code>text</code>
    text = re.sub(r"`(.*?)`", r"<code>\1</code>", text)

    # 4. Улучшение визуальных разделителей
    # Если агент прислал длинную черту из дефисов или подчеркиваний, заменим на красивую
    text = re.sub(r"[-_]{4,}", "────────────────", text)

    return text.strip()

async def is_admin(user_id: int) -> bool:
    if not user_id: return False
    return user_id == config.ADMIN_ID


async def is_whitelisted(user: User) -> bool:
    load_whitelist()
    if not user:
        return False
    # Админ всегда в белом списке, либо проверяем по набору ID
    return await is_admin(user.id) or str(user.id) in whitelist_set
