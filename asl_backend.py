# asl_backend.py
import cv2
import numpy as np
from tensorflow.keras.models import load_model
from hand_tracker import HandTracker
import base64
import io
from PIL import Image
import os
# import uuid # Not needed if speak is removed
# No TTS imports here

# --- Flask Dependencies ---
from flask import Flask, request, jsonify # send_from_directory might not be needed if speak is removed
from flask_cors import CORS

# --- Configuration ---
MODEL_PATH = 'asl_model.h5'
# STATIC_FOLDER = 'static_audio' # Not needed if /api/speak and serving audio are removed
# os.makedirs(STATIC_FOLDER, exist_ok=True) # Not needed

# --- Initialize Flask App ---
app = Flask(__name__) # No static_folder needed if not serving files from here
CORS(app)

# --- Load model and tracker ---
try:
    model = load_model(MODEL_PATH)
    tracker = HandTracker()
    print("ASL Model and Hand Tracker loaded for ASL Backend.")
except Exception as e:
    print(f"ASL Backend: Error loading model or tracker: {e}")
    model = None
    tracker = None

# --- Backend State variables ---
current_word_backend = []
confidence_threshold = 0.8
last_detected_char_info = {"char": "", "confidence": 0.0}

# --- Helper Functions ---
def landmarks_to_feature_vector(landmarks_mp):
    if not landmarks_mp:
        return None
    hand_data = []
    for landmark_obj in landmarks_mp[0].landmark:
        hand_data.extend([landmark_obj.x, landmark_obj.y, landmark_obj.z])
    return hand_data

# --- API Endpoints ---
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "ASL Recognition Backend is running!"})

@app.route('/api/process_frame', methods=['POST'])
def process_frame():
    global last_detected_char_info
    if not model or not tracker:
        return jsonify({"error": "Model or tracker not initialized"}), 500
    data = request.json
    if 'image_data' not in data:
        return jsonify({"error": "No image_data found"}), 400
    try:
        image_b64 = data['image_data'].split(',')[1]
        image_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_bytes))
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    except Exception as e:
        return jsonify({"error": f"Error decoding image: {str(e)}"}), 400
    
    landmarks_mp = tracker.detect_landmarks(frame)
    if landmarks_mp:
        hand_feature_vector = landmarks_to_feature_vector(landmarks_mp)
        if hand_feature_vector:
            try:
                prediction = model.predict(np.array([hand_feature_vector]), verbose=0)
                confidence = float(np.max(prediction))
                predicted_class = np.argmax(prediction)
                if confidence > confidence_threshold:
                    detected_char = chr(65 + predicted_class)
                    last_detected_char_info = {"char": detected_char, "confidence": confidence}
                else:
                    last_detected_char_info = {"char": "", "confidence": confidence, "message": "Low confidence"}
            except Exception as e:
                 return jsonify({"error": f"Error during model prediction: {str(e)}"}), 500
        else:
            last_detected_char_info = {"char": "", "confidence": 0.0, "message": "No hand features extracted"}
    else:
        last_detected_char_info = {"char": "", "confidence": 0.0, "message": "No landmarks detected"}
    return jsonify(last_detected_char_info)

@app.route('/api/get_last_detection', methods=['GET'])
def get_last_detection():
    return jsonify(last_detected_char_info)

@app.route('/api/add_char', methods=['POST'])
def add_char_route():
    global current_word_backend
    data = request.json
    char_to_add = data.get('char', last_detected_char_info.get("char"))
    if char_to_add:
        current_word_backend.append(char_to_add)
    return jsonify({"current_word": "".join(current_word_backend), "added": char_to_add})

@app.route('/api/add_space', methods=['POST'])
def add_space_route():
    global current_word_backend
    current_word_backend.append(' ')
    return jsonify({"current_word": "".join(current_word_backend)})

@app.route('/api/clear_word', methods=['POST'])
def clear_word_route():
    global current_word_backend
    global last_detected_char_info
    current_word_backend = []
    last_detected_char_info = {"char": "", "confidence": 0.0}
    return jsonify({"current_word": ""})

@app.route('/api/get_word', methods=['GET'])
def get_word_route():
    return jsonify({"current_word": "".join(current_word_backend)})

# Removed /api/speak
# Removed /static_audio/<path:filename>

if __name__ == '__main__':
    # This ASL backend runs on port 5000
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)