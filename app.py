import cv2
import time
import threading
import os
from datetime import datetime
from flask import Flask, render_template, Response, jsonify
from ultralytics import YOLO
import mysql.connector
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables (for Twilio keys)
load_dotenv()

# --- DATABASE SETUP ---
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="python_user",     # Your specific database user
        password="Roktim@01",   # Your specific MySQL password
        database="refinery_safety"
    )

# --- TWILIO SETUP ---
def send_sms_alert(hazard_type, confidence):
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        twilio_phone = os.getenv('TWILIO_FROM_NUMBER')
        recipient_phone = os.getenv('TWILIO_TO_NUMBER')

        if not all([account_sid, auth_token, twilio_phone, recipient_phone]):
            print("TWILIO ERROR: Missing credentials in .env file.")
            return

        client = Client(account_sid, auth_token)
        message_body = f"⚠️ URGENT IOCL ALERT: {hazard_type} detected with {confidence}% confidence! Please check the dashboard immediately."
        
        message = client.messages.create(
            body=message_body,
            from_=twilio_phone,
            to=recipient_phone
        )
        print(f"SMS Sent Successfully. SID: {message.sid}")
    except Exception as e:
        print(f"Failed to send SMS: {e}")

# --- AI & APP SETUP ---
app = Flask(__name__)
print("Loading YOLOv8 AI Model... Please wait.")
model = YOLO('models/best.pt')

# Ensure incidents folder exists
if not os.path.exists('static/incidents'):
    os.makedirs('static/incidents')

# --- THREADED CAMERA CLASS (ANTI-LAG FIX) ---
class VideoCamera:
    def __init__(self, src=0):
        print("Initializing Camera...")
        self.stream = cv2.VideoCapture(src)
        if not self.stream.isOpened():
            print("CRITICAL ERROR: Camera could not be opened. Check if another app is using it.")
        
        # Lower resolution to help processor process frames faster
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        # Start the thread to read frames from the video stream
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        # Keep looping infinitely until the thread is stopped
        while not self.stopped:
            (grabbed, frame) = self.stream.read()
            with self.lock:
                self.grabbed = grabbed
                self.frame = frame

    def read(self):
        # Return the latest frame
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()
            return None

    def stop(self):
        self.stopped = True
        self.stream.release()

# Start the threaded camera globally
camera = VideoCamera().start()
time.sleep(1.0) # Give the camera 1 second to warm up

# --- LOGIC VARIABLES ---
last_alert_time = 0
ALERT_COOLDOWN = 30  # Wait 30 seconds before sending another SMS
REQUIRED_THREAT_FRAMES = 3
CONF_THRESHOLD = 0.75
threat_frame_count = 0

def generate_frames():
    global last_alert_time, threat_frame_count
    
    while True:
        # 1. Grab the absolute newest frame from the background thread
        frame = camera.read()
        
        if frame is None:
            time.sleep(0.1)
            continue
            
        # 2. Run the AI Model on this frame
        results = model(frame, stream=True, verbose=False)
        
        hazard_detected = None
        highest_confidence = 0.0
        
        # 3. Analyze Results
        for r in results:
            boxes = r.boxes
            for box in boxes:
                confidence = float(box.conf[0])
                if confidence >= CONF_THRESHOLD:
                    cls = int(box.cls[0])
                    class_name = model.names[cls]
                    
                    # Detect Fire, Smoke, or Vapour
                    if class_name.lower() in ['fire', 'smoke', 'vapour', 'vapor']:
                        hazard_detected = class_name
                        if confidence > highest_confidence:
                            highest_confidence = confidence
                    
                    # Draw Bounding Box dynamically based on threat
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    if class_name.lower() == 'fire':
                        color = (0, 0, 255) # Red
                    elif 'vapour' in class_name.lower() or 'vapor' in class_name.lower():
                        color = (0, 165, 255) # Orange
                    else:
                        color = (150, 150, 150) # Gray for Smoke
                        
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = f"{class_name.upper()} {confidence:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 4. Threat Logic (Persistence & Cooldown)
        if hazard_detected:
            threat_frame_count += 1
            if threat_frame_count >= REQUIRED_THREAT_FRAMES:
                current_time = time.time()
                if current_time - last_alert_time > ALERT_COOLDOWN:
                    print(f"\n[ALERT] {hazard_detected.upper()} detected! Logging and sending SMS...")
                    
                    # Save a snapshot
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"incident_{timestamp_str}.jpg"
                    filepath = os.path.join("static", "incidents", filename)
                    cv2.imwrite(filepath, frame)
                    
                    # Log to DB using the CORRECT column names
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        query = "INSERT INTO incident_logs (hazard_type, confidence_score, snapshot_path) VALUES (%s, %s, %s)"
                        values = (hazard_detected.capitalize() + " Detected", round(highest_confidence * 100, 1), filename)
                        cursor.execute(query, values)
                        conn.commit()
                        cursor.close()
                        conn.close()
                    except Exception as e:
                        print(f"DB Error: {e}")
                    
                    # 'Fire and Forget' Background thread for Twilio (Prevents camera freeze!)
                    threading.Thread(
                        target=send_sms_alert, 
                        args=(hazard_detected.capitalize(), round(highest_confidence * 100, 1)),
                        daemon=True
                    ).start()
                    
                    # Reset timer
                    last_alert_time = current_time
        else:
            # If no hazard seen in this frame, reset the counter
            threat_frame_count = 0

        # 5. Send Frame to Browser
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
            
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# --- WEB ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_recent_logs')
def get_recent_logs():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch recent 5 logs using the correct column names
        cursor.execute("SELECT timestamp, hazard_type, confidence_score, snapshot_path FROM incident_logs ORDER BY timestamp DESC LIMIT 5")
        logs = cursor.fetchall()
        
        # Clean up timestamps for the web UI
        for log in logs:
            if log.get('timestamp'):
                log['timestamp'] = log['timestamp'].strftime("%H:%M:%S")
                
        # 2. Fetch the actual total count of incidents that happened TODAY
        cursor.execute("SELECT COUNT(*) as count FROM incident_logs WHERE DATE(timestamp) = CURDATE()")
        today_count = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        # Return both the logs and the total count securely to JS
        return jsonify({
            "logs": logs,
            "today_count": today_count
        })
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return jsonify({"logs": [], "today_count": 0})

if __name__ == '__main__':
    # Run the server
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)