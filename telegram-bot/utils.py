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
    """Интеллектуальная индексация популярности препаратов с защитой от 'тезок' ДВ"""
    db = Database()
    tavily_api_key = config.TAVILY_API_KEY
    if not tavily_api_key:
        await bot.send_message(chat_id, "❌ API ключ Tavily не найден.")
        return
    
    tavily = TavilyClient(api_key=tavily_api_key)
    log_file = "/app/logs/latest_index.json"
    
    print(f"\n{'='*60}\n🚀 ЗАПУСК ИНДЕКСАЦИИ ПОПУЛЯРНОСТИ (v2: Защита от ДВ)\n{'='*60}", flush=True)
    
    # 0. Загружаем все уникальные названия ДВ для фильтрации тезок
    dv_names_query = "SELECT DISTINCT LOWER(TRIM(jsonb_array_elements(deystvuyushchee_veshchestvo)->>'veshchestvo')) as name FROM reestr.pestitsidy;"
    dv_rows = db.execute_query(dv_names_query)
    all_dv_names = {row['name'] for row in dv_rows if row['name']}
    
    # 1. Получаем уникальные комбинации ДВ и список имен препаратов для каждой
    query = """
    WITH dv_map AS (
        SELECT 
            naimenovanie,
            (SELECT string_agg(sub.name, ' + ' ORDER BY sub.name)
             FROM (SELECT jsonb_array_elements(deystvuyushchee_veshchestvo)->>'veshchestvo' as name) sub
            ) as combination
        FROM reestr.pestitsidy
        WHERE status = 'Действует'
    )
    SELECT combination, array_agg(DISTINCT naimenovanie) as products
    FROM dv_map
    WHERE combination IS NOT NULL
    GROUP BY combination;
    """
    combinations = db.execute_query(query)
    
    if not combinations:
        print("❌ Данные для индексации не найдены в базе.", flush=True)
        await bot.send_message(chat_id, "❌ Данные для индексации не найдены.")
        return

    total_combs = len(combinations)
    print(f"📊 Найдено уникальных комбинаций ДВ: {total_combs}", flush=True)
    await bot.send_message(chat_id, f"🚀 Начинаю умную индексацию ({total_combs} комбинаций ДВ). Препараты-тезки ДВ получат индекс 1.")
    
    db.execute_query("UPDATE reestr.product_popularity SET score = 0;")

    index_data = {
        "timestamp": datetime.now().isoformat(),
        "total_combinations": total_combs,
        "results": []
    }

    processed = 0
    total_found_mentions = 0
    
    for row in combinations:
        dv_text = row['combination']
        product_names = row['products']
        start_time = time.time()
        
        try:
            print(f"🔍 [{processed+1}/{total_combs}] Поиск по ДВ: {dv_text}...", flush=True)
            search_query = f"препараты фунгициды гербициды состав {dv_text}"
            search_result = tavily.search(query=search_query, search_depth="basic", max_results=10)
            
            combined_text = ""
            for r in search_result.get('results', []):
                combined_text += f" {r.get('title', '')} {r.get('content', '')}"
            
            combined_text = combined_text.lower()
            found_in_this_step = []

            for name in product_names:
                # Очищаем имя для сравнения с ДВ и поиска
                # Убираем кавычки и формы выпуска (КЭ, СП, ВДГ и т.д.)
                base_name = name.lower().replace('"', '').replace('«', '').replace('»', '').split(',')[0].strip()
                
                # Правило 1: Если имя совпадает с любым ДВ - индекс 1
                if base_name in all_dv_names:
                    score_to_add = 1
                    # Мы не считаем вхождения в тексте для тезок, чтобы не раздувать индекс
                    mentions = 0 
                else:
                    # Правило 2: Для уникальных имен считаем упоминания
                    mentions = combined_text.count(base_name)
                    score_to_add = mentions

                if score_to_add > 0:
                    upsert_query = f"""
                    INSERT INTO reestr.product_popularity (naimenovanie, score, updated_at)
                    VALUES ('{name.replace("'", "''")}', {score_to_add}, NOW())
                    ON CONFLICT (naimenovanie) DO UPDATE SET score = reestr.product_popularity.score + EXCLUDED.score, updated_at = NOW();
                    """
                    db.execute_query(upsert_query)
                    total_found_mentions += score_to_add
                    found_in_this_step.append(f"{name}({score_to_add})")
            
            if found_in_this_step:
                print(f"   ✅ Найдено: {', '.join(found_in_this_step)}", flush=True)
            
            index_data["results"].append({
                "combination": dv_text,
                "found_products": found_in_this_step
            })
            
            if processed % 10 == 0:
                with open(log_file, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}", flush=True)
            await asyncio.sleep(2)
            
        processed += 1
        if processed % 20 == 0:
            await bot.send_message(chat_id, f"⏳ Обработано {processed} из {total_combs}. Упоминаний: {total_found_mentions}...")
        
        # Строгое соблюдение лимита раз в секунду
        elapsed = time.time() - start_time
        wait_time = max(0.1, 1.1 - elapsed)
        await asyncio.sleep(wait_time)

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}\n✅ ИНДЕКСАЦИЯ ЗАВЕРШЕНА. Всего упоминаний: {total_found_mentions}\n{'='*60}", flush=True)
    await bot.send_message(chat_id, f"✅ Индексация завершена! Всего найдено упоминаний: {total_found_mentions}. Лог в {log_file}")


async def is_admin(user_id: int) -> bool:
    if not user_id: return False
    return user_id == config.ADMIN_ID


async def is_whitelisted(user: User) -> bool:
    load_whitelist()
    if not user:
        return False
    return await is_admin(user.id) or str(user.id) in whitelist_set
