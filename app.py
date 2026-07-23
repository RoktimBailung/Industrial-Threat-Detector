import cv2
from ultralytics import YOLO
from flask import Flask, render_template, jsonify, Response
from alerts import log_incident, send_sms_alert
import time
import os
import mysql.connector

app = Flask(__name__)

# Load the new, highly-trained AI model
print("Loading IOCL Safety AI Engine (YOLOv8s - 50 Epochs)...")
model = YOLO('models/best.pt')

# Tracking variables for automatic alerts
alert_cooldown = 0
COOLDOWN_SECONDS = 30 # Wait 30 seconds between sending automated SMS alerts

# --- Persistence Tracking ---
consecutive_threat_frames = 0
REQUIRED_THREAT_FRAMES = 3  # Threat must be visible for 3 consecutive frames to trigger (Tuned to 0.75)

# Ensure the snapshot directory exists
SNAPSHOT_DIR = os.path.join('static', 'incidents')
if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR)

def generate_frames():
    """Captures webcam frames, runs AI, and streams to dashboard."""
    global alert_cooldown, consecutive_threat_frames
    
    cap = cv2.VideoCapture(0) # Open the webcam
    
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    while True:
        success, frame = cap.read()
        if not success:
            break
            
        # Run YOLOv8 inference on the frame
        # conf=0.75 means 75% confidence required to even draw a box
        results = model(frame, conf=0.75, stream=True)
        annotated_frame = frame
        
        highest_confidence = 0
        hazard_detected = None
        
        for r in results:
            annotated_frame = r.plot() # Draw the boxes
            
            # Check if YOLO found anything dangerous
            for box in r.boxes:
                # box.cls[0] is the class ID (e.g., 0 for Fire, 1 for Smoke)
                # box.conf[0] is the confidence score
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                class_name = model.names[class_id]
                
                if class_name in ["fire", "smoke"] and confidence > highest_confidence:
                    highest_confidence = confidence
                    hazard_detected = class_name
        
        # --- UPGRADED AUTOMATIC ALERT LOGIC ---
        current_time = time.time()
        
        # Check if we see a hazard right now
        if hazard_detected:
            consecutive_threat_frames += 1
        else:
            # If the threat vanishes, reset the counter to prevent false alarms
            consecutive_threat_frames = 0
            
        # Only trigger IF we've seen it consistently AND the cooldown is over
        if consecutive_threat_frames >= REQUIRED_THREAT_FRAMES and (current_time - alert_cooldown > COOLDOWN_SECONDS):
            print(f"⚠️ AUTOMATIC ALERT: {hazard_detected.upper()} DETECTED CONFIRMED! Confidence: {highest_confidence:.2f}")
            
            # --- NEW: Take a Snapshot ---
            timestamp_str = time.strftime("%Y%m%d-%H%M%S")
            filename = f"threat_{hazard_detected}_{timestamp_str}.jpg"
            filepath = os.path.join(SNAPSHOT_DIR, filename)
            
            # Save the image using OpenCV
            cv2.imwrite(filepath, annotated_frame)
            print(f"📸 Snapshot saved to: {filepath}")
            
            # Fire the database and SMS functions! (Pass the filepath!)
            log_incident(hazard_detected.capitalize(), float(f"{highest_confidence:.2f}"), filepath)
            
            # COMMENT OUT THIS LINE TO TEST WITHOUT USING TWILIO CREDITS
            send_sms_alert(hazard_detected.capitalize(), float(f"{highest_confidence:.2f}"))
            
            # Reset the cooldown timer AND the frame counter
            alert_cooldown = current_time
            consecutive_threat_frames = 0

        # Convert the processed frame into JPEG format for web streaming
        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        frame_bytes = buffer.tobytes()

        # Yield the frame in a format HTML can display as a continuous stream
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Route that provides the live AI video stream."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/simulate_threat', methods=['POST'])
def simulate_threat():
    print("WARNING: Simulated Fire Event Triggered!")
    
    # Call the database function
    db_success = log_incident("Fire", 0.95, "N/A")
    
    # Call the Twilio SMS function
    sms_success = send_sms_alert("Fire", 0.95)
    
    if db_success and sms_success:
        return jsonify({"status": "success", "message": "Threat saved to database AND SMS sent!"})
    elif db_success:
        return jsonify({"status": "success", "message": "Threat saved, but SMS failed (check terminal)."})
    else:
        return jsonify({"status": "error", "message": "Database error!"}), 500

# --- Route to fetch live logs ---
@app.route('/get_recent_logs')
def get_recent_logs():
    """Fetches the 5 most recent incidents from the database."""
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='python_user',
            password='Roktim@01',
            database='refinery_safety'
        )
        
        cursor = conn.cursor(dictionary=True)
        # Fetch the 5 most recent logs
        cursor.execute("SELECT hazard_type, confidence_score, snapshot_path, timestamp FROM incident_logs ORDER BY timestamp DESC LIMIT 5")
        logs = cursor.fetchall()
        
        # Format the timestamp for JSON
        for log in logs:
            if log['timestamp']:
                # Handle datetime object formatting safely
                log['timestamp'] = log['timestamp'].strftime("%H:%M:%S")
                
        return jsonify(logs)
        
    except Exception as e:
        print(f"Error fetching live logs: {e}")
        return jsonify([]) # Return empty array so frontend doesn't crash
        
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)