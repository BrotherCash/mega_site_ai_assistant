import sqlite3


class SQLiteDB:
    def __init__(self, db_name):
        self.db_name = db_name
        self.conn = None
        self.cur = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_name)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cur is not None:
            self.cur.close()
        if self.conn is not None:
            self.conn.close()

    def create_table(self, create_table_sql):
        """Создает новую таблицу в базе данных"""
        try:
            self.cur.execute(create_table_sql)
            self.conn.commit()
        except sqlite3.Error as e:
            print(e)

    def insert_into_table(self, table, data):
        """Вставляет данные в таблицу"""
        placeholders = ', '.join(['?'] * len(data))
        sql = f'INSERT INTO {table} VALUES ({placeholders})'
        try:
            self.cur.execute(sql, data)
            self.conn.commit()
        except sqlite3.Error as e:
            print(e)

    def select_from_table(self, table, columns='*', where=None, order_by=None, limit=None):
        """Считывает данные из таблицы"""
        sql = f'SELECT {columns} FROM {table}'
        if where:
            sql += f' WHERE {where}'
        if order_by:
            sql += f' ORDER BY {order_by}'
        if limit:
            sql += f' LIMIT {limit}'
        try:
            self.cur.execute(sql)
            rows = self.cur.fetchall()
            return rows
        except sqlite3.Error as e:
            print(e)

    def update_table(self, table, data, where):
        """Обновляет записи в таблице согласно условию where.
        :param table: имя таблицы
        :param data: словарь, где ключи - имена столбцов, а значения - новые данные для этих столбцов
        :param where: строка условия для обновления (не включая ключевое слово WHERE)
        """
        # Формирование части SQL-запроса с обновляемыми данными
        set_clause = ', '.join([f"{key} = ?" for key in data.keys()])
        # Подготовка SQL-запроса
        sql = f'UPDATE {table} SET {set_clause} WHERE {where}'
        # Выполнение запроса
        try:
            self.cur.execute(sql, tuple(data.values()))
            self.conn.commit()
        except sqlite3.Error as e:
            print(e)

    def delete_from_table(self, table, where=None):
        """Удаляет записи из таблицы согласно условию where.
        :param table: имя таблицы
        :param where: строка условия для удаления (не включая ключевое слово WHERE)
        """
        sql = f'DELETE FROM {table}'
        if where:
            sql += f' WHERE {where}'
        try:
            self.cur.execute(sql)
            self.conn.commit()
        except sqlite3.Error as e:
            print(e)


