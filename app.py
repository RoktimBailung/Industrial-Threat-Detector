from flask import Flask, render_template, jsonify
from alerts import log_incident, send_sms_alert

# Initialize the Flask web server
app = Flask(__name__)

# Route 1: The Main Dashboard
@app.route('/')
def home():
    return render_template('index.html')

# Route 2: The Mock Simulation Endpoint
@app.route('/simulate_threat', methods=['POST'])
def simulate_threat():
    print("WARNING: Simulated Fire Event Triggered!")
    
    # Call the database function
    db_success = log_incident("Fire", 0.95, "N/A")
    
    # --- NEW: Call the Twilio SMS function ---
    sms_success = send_sms_alert("Fire", 0.95)
    
    # We must return a response to the browser!
    if db_success and sms_success:
        return jsonify({"status": "success", "message": "Threat saved to database AND SMS sent!"})
    elif db_success:
        return jsonify({"status": "success", "message": "Threat saved, but SMS failed (check terminal)."})
    else:
        return jsonify({"status": "error", "message": "Database error!"}), 500

# This tells the server to start running when we execute this script
if __name__ == '__main__':
    # debug=True means if you change code and save, the server restarts automatically
    app.run(debug=True, host='127.0.0.1', port=5000)





    
# from flask import Flask, render_template, jsonify
# from alerts import log_incident

# # Initialize the Flask web server
# app = Flask(__name__)

# # Route 1: The Main Dashboard
# # this function runs and serves the HTML file.
# @app.route('/')
# def home():
#     return render_template('index.html')

# # Route 2: The Mock Simulation Endpoint
# # When you click the "Simulate" button on the webpage, it will silently 
# # send a signal here. Later, we will add the Database and SMS code inside here!
# @app.route('/simulate_threat', methods=['POST'])
# def simulate_threat():
#     print("WARNING: Simulated Fire Event Triggered!")
#     # Call the database function
#     db_success = log_incident("Fire", 0.95, "N/A")
#     return jsonify({"status": "success", "message": "Threat saved to database!"})

# # This tells the server to start running when we execute this script
# if __name__ == '__main__':
#     # debug=True means if you change code and save, the server restarts automatically
#     app.run(debug=True, host='127.0.0.1', port=5000)