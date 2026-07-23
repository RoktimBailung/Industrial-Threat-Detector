import cv2
from ultralytics import YOLO

# 1. Load your custom trained model from the models folder
print("Loading the custom Fire & Smoke model...")
model = YOLO("models/best.pt")

# 2. Open the laptop webcam (0 is usually the default built-in camera)
# If 0 doesn't work (if you have multiple cameras), try changing it to 1 or 2
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Could not open webcam.")
    exit()

print("Webcam successfully opened! Look for the separate video window.")
print("Press 'q' on your keyboard while selecting the video window to close it.")

# 3. Process the video stream frame by frame
while True:
    # Read a single frame from the webcam
    success, frame = cap.read()
    
    if not success:
        print("Failed to grab frame.")
        break

    # 4. Feed the frame to your YOLOv8 brain!
    # conf=0.4 means it will only draw a box if it is at least 40% confident
    results = model(frame, conf=0.4, stream=True) 

    # We need a variable to hold the drawn frame. If no objects are found, 
    # it just shows the normal frame.
    annotated_frame = frame 
    
    # 5. Draw the detection boxes on the frame
    for r in results:
        # r.plot() automatically draws the red boxes and labels for us!
        annotated_frame = r.plot() 
        
    # 6. Show the live feed in a new window
    cv2.imshow("IOCL AI Threat Detection Test", annotated_frame)

    # 7. Wait 1 millisecond for the 'q' key to stop the loop
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Closing webcam test...")
        break

# Clean up: release the camera and close the window
cap.release()
cv2.destroyAllWindows()