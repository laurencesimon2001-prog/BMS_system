import mysql.connector
from mysql.connector import Error

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='lucifer',
            password='7812co2Y',
            database='sbms_db',
            autocommit=True 
        )
        return conn
    except Error as e:
        print("DB Connection Error:", e)
        return None

def query_db(query, args=(), one=False):
    conn = get_db_connection()
    if not conn: return None
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, args)
        result = cursor.fetchall()
        return (result[0] if result else None) if one else result
    except Exception as e:
        print("Query Error:", e)
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def execute_db(query, args=()):
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        print(f"DEBUG: Executing SQL -> {query} with {args}")
        cursor.execute(query, args)
        return True
    except Exception as e:
        print(f"DB EXECUTE ERROR: {e}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()