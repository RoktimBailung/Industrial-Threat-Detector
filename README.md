# Industrial Real-Time Threat Detector & Automated Alert Infrastructure

A real-time computer vision safety system designed for industrial environments to detect fire and smoke hazards using localized AI inference, providing instantaneous dashboard warnings and automated emergency notifications.

---

## 🏗️ System Architecture & Data Flow

1. **Video Stream Processing:** The system captures live video frames via a localized hardware webcam or a video file buffer using OpenCV.
2. **AI Inference Pipeline:** Frames are fed into a synchronized Python background thread running a custom-trained YOLOv8 object detection model.
3. **Relational Logging:** Positive hazard detections breaching the confidence threshold trigger an immediate `INSERT` query into a local MySQL database, capturing timestamps, confidence metrics, and image frame paths.
4. **Real-Time Notification Engine:** The backend utilizes Server-Sent Events (SSE) to push instantaneous event dispatches to the frontend dashboard while concurrently triggering an asynchronous webhook payload via the Twilio API to distribute emergency SMS and automated phone call alerts.

---

## 🛠️ Tech Stack

- **Operating System:** Linux Ubuntu 22.04+ (Deployment Match)
- **Backend Framework:** Flask (Python 3.10+)
- **Computer Vision Framework:** OpenCV & Ultralytics YOLOv8
- **Database Management:** MySQL Server
- **Third-Party APIs:** Twilio API (SMS & Voice Notification Gateway)

---
