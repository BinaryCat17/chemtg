import config
from database import Database

db = Database()

def get_system_prompt():
    """Собирает системный промпт из файла, вставляя схему БД и пользовательские инструкции"""
    db_schema = db.get_schema()
    
    # Берем базовый системный промпт из конфига
    system_base = config.current_system_prompt
    
    # Вставляем схему и пользовательский промпт
    return system_base.format(
        db_schema=db_schema, 
        user_prompt=config.current_user_prompt
    )
