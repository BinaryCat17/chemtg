import config
from config import whitelist_set, load_whitelist, log_prompt
from aiogram.types import User
import re
import html
import asyncio
import json
import os
import time
from datetime import datetime
from tavily import TavilyClient
from database import Database


def format_for_telegram(text: str) -> str:
    """
    Преобразует Markdown в безопасный HTML для Telegram.
    Поддерживает жирный текст, курсив, моноширинный шрифт и списки.
    """
    if not text:
        return text

    # 1. Сначала очищаем текст от возможных "грязных" тегов
    text = html.escape(text)

    # 2. Восстанавливаем теги, которые МЫ РАЗРЕШИЛИ
    text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    text = text.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    text = text.replace("&lt;pre&gt;", "<pre>").replace("&lt;/pre&gt;", "</pre>")

    # 3. Обработка Markdown синтаксиса
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.*?)__", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"`(.*?)`", r"<code>\1</code>", text)

    # 4. Улучшение визуальных разделителей
    text = re.sub(r"[-_]{4,}", "────────────────", text)

    return text.strip()


async def index_all_products_popularity(bot, chat_id):
    """Индексация популярности на основе размера портфеля компаний и новизны препаратов"""
    db = Database()
    
    print(f"\n{'='*60}\n🚀 ЗАПУСК ИНДЕКСАЦИИ ПОПУЛЯРНОСТИ (v3: Портфель + Новизна)\n{'='*60}", flush=True)
    await bot.send_message(chat_id, "🚀 Начинаю индексацию популярности (анализ портфеля компаний и новизны препаратов)...")
    
    # Создаем таблицы, если их нет
    db.execute_query("CREATE TABLE IF NOT EXISTS product_popularity (naimenovanie TEXT PRIMARY KEY, score INTEGER DEFAULT 0, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    db.execute_query("CREATE TABLE IF NOT EXISTS agrokhimikaty_popularity (preparat TEXT PRIMARY KEY, score INTEGER DEFAULT 0, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    
    # Сброс старых очков
    db.execute_query("UPDATE product_popularity SET score = 0;")
    db.execute_query("UPDATE agrokhimikaty_popularity SET score = 0;")

    # 1. Индексация Пестицидов
    print("🏢 Анализ портфеля и новизны пестицидов...", flush=True)
    # Формула: LOG10(кол-во препаратов компании) * 3 + Бонус за новизну (регистрация 2024-2026 = +2, 2022-2023 = +1)
    db.execute_query("""
    WITH company_counts AS (
        SELECT registrant, COUNT(*) as p_count 
        FROM pestitsidy 
        WHERE status = 'Действует' 
        GROUP BY registrant
    ),
    product_scores AS (
        SELECT 
            p.naimenovanie, 
            MAX(ROUND(LOG(c.p_count + 1) * 3)) as portfolio_bonus,
            CASE 
                WHEN p.data_reg REGEXP '2024|2025|2026' THEN 2
                WHEN p.data_reg REGEXP '2022|2023' THEN 1
                ELSE 0
            END as novelty_bonus
        FROM pestitsidy p
        JOIN company_counts c ON p.registrant = c.registrant
        WHERE p.status = 'Действует'
        GROUP BY p.naimenovanie
    )
    INSERT INTO product_popularity (naimenovanie, score, updated_at)
    SELECT naimenovanie, (portfolio_bonus + novelty_bonus), CURRENT_TIMESTAMP
    FROM product_scores
    ON CONFLICT (naimenovanie) DO UPDATE SET score = EXCLUDED.score, updated_at = CURRENT_TIMESTAMP;
    """)

    # 2. Индексация Агрохимикатов
    print("🌱 Анализ портфеля и новизны агрохимикатов...", flush=True)
    db.execute_query("""
    WITH company_counts AS (
        SELECT registrant, COUNT(*) as p_count 
        FROM agrokhimikaty 
        WHERE status = 'Действует' 
        GROUP BY registrant
    ),
    product_scores AS (
        SELECT 
            p.preparat, 
            MAX(ROUND(LOG(c.p_count + 1) * 3)) as portfolio_bonus,
            CASE 
                WHEN p.data_reg REGEXP '2024|2025|2026' THEN 2
                WHEN p.data_reg REGEXP '2022|2023' THEN 1
                ELSE 0
            END as novelty_bonus
        FROM agrokhimikaty p
        JOIN company_counts c ON p.registrant = c.registrant
        WHERE p.status = 'Действует'
        GROUP BY p.preparat
    )
    INSERT INTO agrokhimikaty_popularity (preparat, score, updated_at)
    SELECT preparat, (portfolio_bonus + novelty_bonus), CURRENT_TIMESTAMP
    FROM product_scores
    ON CONFLICT (preparat) DO UPDATE SET score = EXCLUDED.score, updated_at = CURRENT_TIMESTAMP;
    """)

    await bot.send_message(chat_id, "✅ Индексация завершена! Рейтинг пересчитан с учетом размера компаний (сглажено) и новизны регистраций.")

    await bot.send_message(chat_id, f"✅ Индексация завершена! Найдено упоминаний: {total_found_mentions}. Также добавлены бонусы по размеру портфеля компаний для пестицидов и агрохимикатов. Лог в {log_file}")


async def is_admin(user_id: int) -> bool:
    if not user_id: return False
    return user_id == config.ADMIN_ID


async def is_whitelisted(user: User) -> bool:
    load_whitelist()
    if not user:
        return False
    return await is_admin(user.id) or str(user.id) in whitelist_set
