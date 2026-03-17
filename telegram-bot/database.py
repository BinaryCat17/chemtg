import sqlite3
import os

class Database:
    def __init__(self):
        # По умолчанию создаем файл reestr.db в корне папки бота
        self.db_path = os.getenv('SQLITE_DB_PATH', 'reestr.db')
        self.conn = None

    def _connect(self):
        if self.conn is None:
            # Создаем соединение. check_same_thread=False нужен для работы в разных потоках asyncio
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Включаем возврат словарей (доступ по именам колонок)
            self.conn.row_factory = sqlite3.Row
            
            # Добавляем поддержку REGEXP и нормальный LOWER для кириллицы
            import re
            def regexp(expr, item):
                if item is None: return False
                reg = re.compile(expr, re.IGNORECASE)
                return reg.search(str(item)) is not None
            
            self.conn.create_function("REGEXP", 2, regexp)
            self.conn.create_function("LOWER", 1, lambda x: str(x).lower() if x is not None else None)
            self.conn.create_function("UPPER", 1, lambda x: str(x).upper() if x is not None else None)
        return self.conn

    def execute_query(self, query: str):
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(query)
            
            # Если это SELECT запрос
            if query.strip().upper().startswith("SELECT"):
                rows = cur.fetchall()
                # Превращаем sqlite3.Row в обычные словари для совместимости с логикой бота
                return [dict(row) for row in rows]
            
            # Для модифицирующих запросов (INSERT/UPDATE/DELETE)
            conn.commit()
            return {"status": "success"}
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            return {"error": str(e)}

    def get_schema(self):
        """Возвращает описание таблиц SQLite для AI-промпта"""
        try:
            conn = self._connect()
            cur = conn.cursor()
            
            # Получаем список всех таблиц, созданных пользователем
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = cur.fetchall()
            
            if not tables:
                return "Database is empty. No tables found."

            schema_text = "Database schema (SQLite):\n"
            for table in tables:
                table_name = table['name']
                schema_text += f"\nTable: {table_name}\n"
                
                # Получаем инфо о колонках (cid, name, type, notnull, dflt_value, pk)
                cur.execute(f"PRAGMA table_info({table_name});")
                columns = cur.fetchall()
                for col in columns:
                    schema_text += f" - {col['name']} ({col['type']})\n"
            
            return schema_text
        except Exception as e:
            return f"Error retrieving schema: {str(e)}"

    def __del__(self):
        if self.conn:
            self.conn.close()
