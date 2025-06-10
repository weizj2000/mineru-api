import os
import sqlite3
import psycopg2
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from psycopg2 import OperationalError
from sqlite3 import Error as SQLiteError


def _build_where_clause(conditions: Dict[str, any]) -> Tuple[str, tuple]:
    """通用构建WHERE子句的辅助函数"""
    where_parts = [f"{k} = %s" if isinstance(k, str) else f"{k} = %s" for k in conditions.keys()]
    return " AND ".join(where_parts), tuple(conditions.values())


def _build_set_clause(data: Dict[str, any]) -> Tuple[str, tuple]:
    """通用构建SET子句的辅助函数"""
    set_parts = [f"{k} = %s" if isinstance(k, str) else f"{k} = %s" for k in data.keys()]
    return ", ".join(set_parts), tuple(data.values())


class DBManager(ABC):
    """数据库管理器抽象基类，定义数据库操作接口"""

    @abstractmethod
    def __init__(self, connection_params: Dict[str, str]):
        pass

    @abstractmethod
    def create_table(self, table_name: str, columns: Dict[str, str]) -> bool:
        """
        创建数据库表

        Args:
            table_name: 表名
            columns: 列定义字典（列名: 数据类型）

        Returns:
            bool: 是否创建成功
        """
        pass

    @abstractmethod
    def execute(self, sql: str, params: Optional[tuple] = None) -> bool:
        """
        执行非查询类SQL语句（INSERT/UPDATE/DELETE）

        Args:
            sql: SQL语句
            params: 参数元组

        Returns:
            bool: 是否执行成功
        """
        pass

    @abstractmethod
    def fetchall(self, sql: str, params: Optional[tuple] = None) -> List[tuple]:
        """
        执行查询类SQL语句并返回所有结果

        Args:
            sql: SQL语句
            params: 参数元组

        Returns:
            List[tuple]: 查询结果列表
        """
        pass

    @abstractmethod
    def create(self, table: str, data: Dict[str, any]) -> bool:
        """
        插入新记录

        Args:
            table: 表名
            data: 数据字典（列名: 值）

        Returns:
            bool: 是否插入成功
        """
        pass

    @abstractmethod
    def read(self, table: str, conditions: Optional[Dict[str, any]] = None) -> List[tuple]:
        """
        查询记录

        Args:
            table: 表名
            conditions: 查询条件字典（列名: 值）

        Returns:
            List[tuple]: 查询结果
        """
        pass

    @abstractmethod
    def update(self, table: str, data: Dict[str, any], conditions: Dict[str, any]) -> bool:
        """
        更新记录

        Args:
            table: 表名
            data: 要更新的数据字典（列名: 新值）
            conditions: 更新条件字典（列名: 条件值）

        Returns:
            bool: 是否更新成功
        """
        pass

    @abstractmethod
    def delete(self, table: str, conditions: Dict[str, any]) -> bool:
        """
        删除记录

        Args:
            table: 表名
            conditions: 删除条件字典（列名: 条件值）

        Returns:
            bool: 是否删除成功
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭数据库连接"""
        pass


class SQLiteDBManager(DBManager):
    """SQLite数据库管理器实现"""

    def __init__(self, connection_params: Dict[str, str]):
        self.db_path = connection_params.get('db_path', 'default.db')
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
        except SQLiteError as e:
            raise ConnectionError(f"SQLite连接失败: {str(e)}")

    def create_table(self, table_name: str, columns: Dict[str, str]) -> bool:
        column_defs = ", ".join([f"{k} {v}" for k, v in columns.items()])
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({column_defs})"
        return self.execute(sql)

    def execute(self, sql: str, params: Optional[tuple] = None) -> bool:
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            self.conn.commit()
            return True
        except SQLiteError as e:
            print(f"SQLite执行错误: {str(e)}")
            return False

    def fetchall(self, sql: str, params: Optional[tuple] = None) -> List[tuple]:
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            return self.cursor.fetchall()
        except SQLiteError as e:
            print(f"SQLite查询错误: {str(e)}")
            return []

    def create(self, table: str, data: Dict[str, any]) -> bool:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        return self.execute(sql, tuple(data.values()))

    def read(self, table: str, conditions: Optional[Dict[str, any]] = None) -> List[tuple]:
        sql = f"SELECT * FROM {table}"
        if conditions:
            where_clause, params = _build_where_clause(conditions)
            sql += f" WHERE {where_clause}"
        else:
            params = None
        return self.fetchall(sql, params)

    def update(self, table: str, data: Dict[str, any], conditions: Dict[str, any]) -> bool:
        set_clause, set_params = _build_set_clause(data)
        where_clause, where_params = _build_where_clause(conditions)
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        return self.execute(sql, set_params + where_params)

    def delete(self, table: str, conditions: Dict[str, any]) -> bool:
        where_clause, params = _build_where_clause(conditions)
        sql = f"DELETE FROM {table} WHERE {where_clause}"
        return self.execute(sql, params)

    def close(self) -> None:
        self.conn.close()


class PostgresDBManager(DBManager):
    """PostgreSQL数据库管理器实现"""

    def __init__(self, connection_params: Dict[str, str]):
        self.conn = None
        try:
            self.conn = psycopg2.connect(
                dbname=connection_params['dbname'],
                user=connection_params['user'],
                password=connection_params.get('password', ''),
                host=connection_params.get('host', 'localhost'),
                port=connection_params.get('port', '5432')
            )
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            raise ConnectionError(f"PostgreSQL连接失败: {str(e)}")

    def create_table(self, table_name: str, columns: Dict[str, str]) -> bool:
        column_defs = ", ".join([f"{k} {v}" for k, v in columns.items()])
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({column_defs})"
        return self.execute(sql)

    def execute(self, sql: str, params: Optional[tuple] = None) -> bool:
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"PostgreSQL执行错误: {str(e)}")
            return False

    def fetchall(self, sql: str, params: Optional[tuple] = None) -> List[tuple]:
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"PostgreSQL查询错误: {str(e)}")
            return []

    def create(self, table: str, data: Dict[str, any]) -> bool:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(['%s' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        return self.execute(sql, tuple(data.values()))

    def read(self, table: str, conditions: Optional[Dict[str, any]] = None) -> List[tuple]:
        sql = f"SELECT * FROM {table}"
        if conditions:
            where_clause, params = _build_where_clause(conditions)
            sql += f" WHERE {where_clause}"
        else:
            params = None
        return self.fetchall(sql, params)

    def update(self, table: str, data: Dict[str, any], conditions: Dict[str, any]) -> bool:
        set_clause, set_params = _build_set_clause(data)
        where_clause, where_params = _build_where_clause(conditions)
        sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        return self.execute(sql, set_params + where_params)

    def delete(self, table: str, conditions: Dict[str, any]) -> bool:
        where_clause, params = _build_where_clause(conditions)
        sql = f"DELETE FROM {table} WHERE {where_clause}"
        return self.execute(sql, params)

    def close(self) -> None:
        self.cursor.close()
        self.conn.close()


class DBManagerFactory:
    """数据库管理器工厂类"""

    @staticmethod
    def create_db_manager(db_type: str = "sqlite", **kwargs) -> DBManager:
        """
        创建数据库管理器实例

        Args:
            db_type: 数据库类型（'sqlite'或'postgres'）
            **kwargs: 数据库连接参数

        Returns:
            DBManager: 数据库管理器实例
        """
        db_type = db_type.lower()
        if db_type == 'sqlite':
            return SQLiteDBManager(kwargs)
        elif db_type == 'postgres':
            return PostgresDBManager(kwargs)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

