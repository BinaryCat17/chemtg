import sqlite3
import os

class Database:
    def __init__(self, db_path="reestr.db"):
        self.db_path = os.getenv('SQLITE_DB_PATH', db_path)
        self.conn = None

    def _connect(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            # Включаем возврат словарей вместо кортежей
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def execute_query(self, query: str):
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(query)
            
            # Если запрос SELECT, возвращаем данные
            if query.strip().upper().startswith("SELECT"):
                rows = cur.fetchall()
                # Превращаем Row-объекты в обычные словари для совместимости с кодом
                return [dict(row) for row in rows]
            
            # Для INSERT/UPDATE/DELETE фиксируем изменения
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            return {"error": str(e)}

    def get_schema(self):
        """Возвращает описание всех таблиц для AI промпта (версия SQLite)"""
        try:
            conn = self._connect()
            cur = conn.cursor()
            
            # Получаем список всех таблиц
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = cur.fetchall()
            
            schema_text = "Database schema (SQLite):\n"
            for table in tables:
                table_name = table['name']
                schema_text += f"\nTable: {table_name}\n"
                
                # Получаем колонки для каждой таблицы
                cur.execute(f"PRAGMA table_info({table_name});")
                columns = cur.fetchall()
                for col in columns:
                    # col[1] - имя, col[2] - тип
                    schema_text += f" - {col[1]} ({col[2]})\n"
            
            return schema_text
        except Exception as e:
            return f"Error retrieving schema: {str(e)}"

    def __del__(self):
        if self.conn:
            self.conn.close()
