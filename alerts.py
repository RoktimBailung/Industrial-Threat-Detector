import os
import mysql.connector
from datetime import datetime
from twilio.rest import Client
from dotenv import load_dotenv

# Load the secret keys from the hidden .env file
load_dotenv()

# --- IMPORTANT: DATABASE CONFIGURATION ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'python_user',
    'password': 'Roktim@01', 
    'database': 'refinery_safety'
}

# --- IMPORTANT: TWILIO CONFIGURATION ---

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER')
TWILIO_TO_NUMBER = os.getenv('TWILIO_TO_NUMBER')

def send_sms_alert(hazard_type, confidence_score):
    """Sends an SMS alert using Twilio."""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message_body = f"🚨 IOCL ALERT: {hazard_type} detected with {confidence_score*100}% confidence! Check dashboard."
        
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_FROM_NUMBER,
            to=TWILIO_TO_NUMBER
        )
        print(f"📱 SUCCESS: SMS sent! Message SID: {message.sid}")
        return True
    except Exception as e:
        print(f"❌ Twilio SMS Error: {e}")
        return False

def log_incident(hazard_type, confidence_score, snapshot_path):
    """Saves a threat event into the MySQL database using existing columns."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        
        sql = "INSERT INTO incident_logs (hazard_type, confidence_score, snapshot_path) VALUES (%s, %s, %s)"
        val = (hazard_type, confidence_score, snapshot_path)
        
        cursor.execute(sql, val)
        conn.commit()
        
        print(f"SUCCESS: Logged [{hazard_type}] with confidence [{confidence_score}] into MySQL!")
        return True
        
    except mysql.connector.Error as err:
        print(f"Database Insertion Error: {err}")
        return False
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"\n MySQL Connection Error: {err}")
        return None