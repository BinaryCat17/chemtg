import config
from database import Database

db = Database()

def get_system_prompt():
    """Собирает системный промпт из файла, вставляя схему БД и пользовательские инструкции"""
    db_schema = db.get_schema()
    
    # Получаем текущую дату
    from datetime import datetime
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    # Пытаемся получить дату последнего импорта из базы
    try:
        query = "SELECT MAX(imported_at) as last_update FROM pestitsidy;"
        res = db.execute_query(query)
        if isinstance(res, list) and res[0]['last_update']:
            last_update_date = res[0]['last_update'].strftime("%d.%m.%Y %H:%M")
        else:
            last_update_date = "Неизвестно"
    except:
        last_update_date = "Ошибка при получении"
    
    # Берем базовый системный промпт из конфига
    system_base = config.current_system_prompt
    
    # Вставляем схему, пользовательский промпт и даты
    return system_base.format(
        db_schema=db_schema, 
        user_prompt=config.current_user_prompt,
        current_date=current_date,
        last_update_date=last_update_date
    )
