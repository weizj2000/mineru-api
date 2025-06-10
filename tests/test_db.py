from app.services.db_manager import DBManagerFactory

class TestSQLiteDB:
    
    def setup_method(self):
        sqlite_manager = DBManagerFactory.create_db_manager('sqlite', db_path='test.db')
        sqlite_manager.create_table('users', {'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT', 'age': 'INTEGER'})
        sqlite_manager.create('users', {'name': 'Alice', 'age': 30})
        print("SQLite查询结果:", sqlite_manager.read('users'))
        sqlite_manager.close()
        
        
class TestPostgresDB:

    def setup_method(self):
        pg_manager = DBManagerFactory.create_db_manager('postgres',
            dbname='mydb',
            user='postgres',
            password='password',
            host='localhost',
            port='5432'
        )
        pg_manager.create_table('users', {'id': 'SERIAL PRIMARY KEY', 'name': 'VARCHAR(50)', 'age': 'INTEGER'})
        pg_manager.create('users', {'name': 'Bob', 'age': 25})
        print("PostgreSQL查询结果:", pg_manager.read('users'))
        pg_manager.close()
