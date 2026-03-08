import os
import psycopg2
from psycopg2.extras import RealDictCursor

class Database:
    def __init__(self):
        self.host = os.getenv('POSTGRES_HOST', 'postgres')
        self.port = os.getenv('POSTGRES_PORT', '5432')
        self.dbname = os.getenv('POSTGRES_DB', 'reestr')
        self.user = os.getenv('POSTGRES_USER', 'postgres')
        self.password = os.getenv('POSTGRES_PASSWORD', 'ChangeMe2026!!')
        self.schema = os.getenv('POSTGRES_SCHEMA', 'reestr')
        self.conn = None

    def _connect(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password
            )
        return self.conn

    def execute_query(self, query: str):
        try:
            conn = self._connect()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)
                if cur.description:
                    return cur.fetchall()
                conn.commit()
                return {"status": "success"}
        except Exception as e:
            if self.conn and not self.conn.closed:
                try:
                    self.conn.rollback()
                except:
                    pass
            return {"error": str(e)}

    def get_schema(self):
        """Возвращает описание таблиц для промпта"""
        schema_query = f"""
        SELECT table_name, column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = '{self.schema}'
        ORDER BY table_name, ordinal_position;
        """
        results = self.execute_query(schema_query)
        if isinstance(results, dict) and "error" in results:
            return "Error retrieving schema"
        
        schema_text = f"Database schema:\n"
        current_table = ""
        for row in results:
            if row['table_name'] != current_table:
                current_table = row['table_name']
                schema_text += f"\nTable: {self.schema}.{current_table}\n"
            schema_text += f" - {row['column_name']} ({row['data_type']})\n"
        return schema_text
