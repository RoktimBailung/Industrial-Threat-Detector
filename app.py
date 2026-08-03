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

# DATABASE SETUP 
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="python_user",     
        password="Roktim@01",   
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
print("Loading Intel-Optimized YOLOv11 Engine... Please wait.")

# Explicitly passing task='detect' silences the terminal warning
model = YOLO('models/best_openvino_model', task='detect')

# Ensure incidents folder exists
if not os.path.exists('static/incidents'):
    os.makedirs('static/incidents')

# --- THREADED CAMERA CLASS (HARDWARE-ACCELERATED) ---
class VideoCamera:
    def __init__(self, src=0):
        print("Initializing Camera Stream...")
        self.stream = cv2.VideoCapture(src)
        if not self.stream.isOpened():
            print("CRITICAL ERROR: Camera could not be opened. Check hardware connections.")
        
        # Optimize frame resolution for edge processing
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Eliminate frame queue buffer delay
        self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        # Start thread to read frames continuously from the video stream
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        # Continuous frame extraction thread
        while not self.stopped:
            (grabbed, frame) = self.stream.read()
            with self.lock:
                self.grabbed = grabbed
                self.frame = frame
            time.sleep(0.01)  # Yield CPU execution slice

    def read(self):
        # Fetch latest captured frame
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()
            return None

    def stop(self):
        self.stopped = True
        self.stream.release()

# Start the threaded camera globally
camera = VideoCamera().start()
time.sleep(1.0) # Warm up camera module

# --- LOGIC VARIABLES ---
last_alert_time = 0
ALERT_COOLDOWN = 30  # Seconds before dispatching next SMS
REQUIRED_THREAT_FRAMES = 3
CONF_THRESHOLD = 0.75
threat_frame_count = 0

def generate_frames():
    global last_alert_time, threat_frame_count
    frame_counter = 0
    cached_boxes = []  # Bounding box cache for frame-skipping rendering
    
    while True:
        # 1. Fetch real-time frame from threaded camera buffer
        frame = camera.read()
        
        if frame is None:
            time.sleep(0.01)
            continue
            
        frame_counter += 1
        
        # 2. Run inference on alternating frames for maximum stream smoothness
        if frame_counter % 2 == 0:
            results = model(frame, stream=True, verbose=False)
            
            hazard_detected = None
            highest_confidence = 0.0
            new_cached_boxes = []
            
            # 3. Analyze Detections
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    confidence = float(box.conf[0])
                    
                    cls = int(box.cls[0])
                    class_name = model.names[cls]
                    
                    # Target Threat Classes
                    if class_name.lower() in ['fire', 'smoke', 'vapour', 'vapor']:
                        
                        # Set Bounding Box Colors (Draw them even if below SMS threshold)
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        if class_name.lower() == 'fire':
                            color = (0, 0, 255) # Red
                        elif 'vapour' in class_name.lower() or 'vapor' in class_name.lower():
                            color = (0, 165, 255) # Orange
                        else:
                            color = (150, 150, 150) # Gray for Smoke
                            
                        label = f"{class_name.upper()} {confidence:.2f}"
                        new_cached_boxes.append((x1, y1, x2, y2, color, label))

                        # --- SMS TRIGGER LOGIC ---
                        if confidence >= CONF_THRESHOLD:
                            hazard_detected = class_name
                            if confidence > highest_confidence:
                                highest_confidence = confidence
                            print(f"[LIVE AI DEBUG] Verified {class_name.upper()} at {confidence*100:.1f}%")

            cached_boxes = new_cached_boxes

            # 4. Persistence Verification & Autonomous Alerting
            if hazard_detected:
                # Trigger immediately on the first high-confidence frame
                current_time = time.time()
                if current_time - last_alert_time > ALERT_COOLDOWN:
                    print(f"\n[EVENT] {hazard_detected.upper()} confirmed by YOLOv11! Logging incident...")
                    
                    # Generate snapshot with drawn detections
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"incident_{timestamp_str}.jpg"
                    filepath = os.path.join("static", "incidents", filename)
                    
                    snapshot_frame = frame.copy()
                    for (x1, y1, x2, y2, color, label) in cached_boxes:
                        cv2.rectangle(snapshot_frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(snapshot_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    
                    cv2.imwrite(filepath, snapshot_frame)
                    
                    # Log incident to MySQL database
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
                    
                    # Only send SMS if the hazard is NOT vapour/vapor
                    if hazard_detected.lower() not in ['vapour', 'vapor']:
                        print("Dispatching urgent Twilio SMS...")
                        threading.Thread(
                            target=send_sms_alert, 
                            args=(hazard_detected.capitalize(), round(highest_confidence * 100, 1)),
                            daemon=True
                        ).start()
                    else:
                        print("SMS bypassed for Vapour (Routine visual anomaly).")
                    
                    last_alert_time = current_time
                    
        else:
            threat_frame_count = 0

        # Draw cached bounding boxes onto stream output
        for (x1, y1, x2, y2, color, label) in cached_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 5. Stream Output Encoding
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
        
        # Retrieve 5 most recent incident records
        cursor.execute("SELECT timestamp, hazard_type, confidence_score, snapshot_path FROM incident_logs ORDER BY timestamp DESC LIMIT 5")
        logs = cursor.fetchall()
        
        for log in logs:
            if log.get('timestamp'):
                log['timestamp'] = log['timestamp'].strftime("%H:%M:%S")
                
        # Retrieve total incident count recorded today
        cursor.execute("SELECT COUNT(*) as count FROM incident_logs WHERE DATE(timestamp) = CURDATE()")
        today_count = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "logs": logs,
            "today_count": today_count
        })
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return jsonify({"logs": [], "today_count": 0})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)