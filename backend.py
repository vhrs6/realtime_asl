import cv2
import numpy as np
from tensorflow.keras.models import load_model
from hand_tracker import HandTracker  # Ensure this module is available
import base64
import io
from PIL import Image
import os
import uuid # For unique filenames

# --- TTS Dependencies ---
from kokoro import KPipeline
# from IPython.display import display, Audio # Not needed for backend
import soundfile as sf

# --- Flask Dependencies ---
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# --- Configuration ---
LANGUAGE_CODE = 'a'  # English
VOICE_MODEL = 'am_fenrir'
SAMPLE_RATE = 24000
MODEL_PATH = 'asl_model.h5' # Make sure this path is correct
STATIC_FOLDER = 'static_audio' # For serving generated audio
os.makedirs(STATIC_FOLDER, exist_ok=True)

# --- Initialize Flask App ---
app = Flask(__name__, static_folder=STATIC_FOLDER)
CORS(app) # Enable CORS for all routes

# --- Initialize TTS Pipeline ---
try:
    print(f"Initializing Kokoro Pipeline with lang='{LANGUAGE_CODE}'...")
    pipeline = KPipeline(lang_code=LANGUAGE_CODE)
    print("Pipeline initialized.")
except Exception as e:
    print(f"Error initializing Kokoro pipeline: {e}")
    pipeline = None # Handle gracefully if TTS fails to init

# --- Load model and tracker ---
try:
    model = load_model(MODEL_PATH)
    tracker = HandTracker()
    print("ASL Model and Hand Tracker loaded.")
except Exception as e:
    print(f"Error loading model or tracker: {e}")
    model = None
    tracker = None

# --- Backend State variables ---
current_word_backend = []
confidence_threshold = 0.8
last_detected_char_info = {"char": "", "confidence": 0.0} # Store last detection

# --- Helper Functions ---
def landmarks_to_feature_vector(landmarks_mp):
    """Converts MediaPipe landmarks to a flat list for the model."""
    if not landmarks_mp:
        return None
    hand_data = []
    # Assuming landmarks_mp is a list of landmark lists (one per hand)
    # And we are interested in the first hand found.
    for landmark_obj in landmarks_mp[0].landmark: # Accessing the .landmark attribute
        hand_data.extend([landmark_obj.x, landmark_obj.y, landmark_obj.z])
    return hand_data

# --- API Endpoints ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "ASL Translator Backend is running!"})

@app.route('/api/process_frame', methods=['POST'])
def process_frame():
    global last_detected_char_info
    if not model or not tracker:
        return jsonify({"error": "Model or tracker not initialized"}), 500

    data = request.json
    if 'image_data' not in data:
        return jsonify({"error": "No image_data found"}), 400

    # Decode base64 image
    try:
        image_b64 = data['image_data'].split(',')[1] # Remove "data:image/jpeg;base64,"
        image_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_bytes))
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR) # CV2 uses BGR
    except Exception as e:
        return jsonify({"error": f"Error decoding image: {str(e)}"}), 400

    # Perform detection (frame is already flipped by frontend if needed)
    # frame = cv2.flip(frame, 1) # If frontend doesn't flip
    landmarks_mp = tracker.detect_landmarks(frame) # This should return mediapipe landmark objects

    detected_char = ""
    confidence = 0.0

    if landmarks_mp:
        # Assuming landmarks_mp is a list, and we take the first detected hand
        # Also assuming tracker.detect_landmarks returns the raw mediapipe landmark list
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
    last_detected_char_info = {"char": "", "confidence": 0.0} # Reset last detection too
    return jsonify({"current_word": ""})

@app.route('/api/get_word', methods=['GET'])
def get_word_route():
    return jsonify({"current_word": "".join(current_word_backend)})

@app.route('/api/speak', methods=['POST'])
def speak_route():
    if not pipeline:
        return jsonify({"error": "TTS Pipeline not initialized"}), 500

    data = request.json
    text_to_speak = data.get("text", "".join(current_word_backend)).strip()

    if not text_to_speak:
        return jsonify({"error": "No text to speak"}), 400

    try:
        print(f"Backend: Generating audio for: {text_to_speak}")
        generator = pipeline(text_to_speak, voice=VOICE_MODEL)
        all_audio_chunks = []
        for i, (_, _, audio_chunk) in enumerate(generator):
            if audio_chunk is not None and len(audio_chunk) > 0:
                all_audio_chunks.append(audio_chunk)

        if all_audio_chunks:
            complete_audio = np.concatenate(all_audio_chunks)
            filename = f"speech_{uuid.uuid4().hex}.wav"
            filepath = os.path.join(STATIC_FOLDER, filename)
            sf.write(filepath, complete_audio, SAMPLE_RATE)
            audio_url = request.host_url + f"{STATIC_FOLDER}/{filename}" # Construct full URL
            print(f"Audio saved to {filepath}, URL: {audio_url}")
            return jsonify({"audio_url": audio_url, "text_spoken": text_to_speak})
        else:
            return jsonify({"error": "TTS generated no audio"}), 500
    except Exception as e:
        print(f"Error generating audio: {e}")
        return jsonify({"error": f"Error generating audio: {str(e)}"}), 500

# Serve static audio files
@app.route(f'/{STATIC_FOLDER}/<path:filename>')
def serve_static_audio(filename):
    return send_from_directory(app.static_folder, filename)


if __name__ == '__main__':
    print(f"Audio files will be served from: {os.path.abspath(STATIC_FOLDER)}")
    app.run(debug=True, host='0.0.0.0', port=5000) # Accessible on your network