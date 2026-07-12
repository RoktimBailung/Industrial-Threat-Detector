import mysql.connector

try:
    conn = mysql.connector.connect(
        host='localhost',
        user='python_user',
        password='Roktim@01',
        database='refinery_safety'
    )
    cursor = conn.cursor()
    cursor.execute("SELECT DATABASE();")
    print(f"Connected to DB: {cursor.fetchone()[0]}")
    cursor.execute("SELECT count(*) FROM incident_logs;")
    print(f"Total rows in incident_logs: {cursor.fetchone()[0]}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")