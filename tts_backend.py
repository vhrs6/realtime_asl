# tts_backend.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import numpy as np
import os
import uuid

# --- TTS Dependencies ---
from kokoro import KPipeline # Ensure kokoro is importable
import soundfile as sf

# --- Configuration ---
LANGUAGE_CODE = 'a'  # English
VOICE_MODEL = 'am_fenrir'
SAMPLE_RATE = 24000
# Use a distinct static folder for this backend's audio files
TTS_STATIC_FOLDER = 'static_audio_tts_service' 
os.makedirs(TTS_STATIC_FOLDER, exist_ok=True)

# --- Initialize Flask App for TTS Service ---
app = Flask(__name__, static_folder=TTS_STATIC_FOLDER)
CORS(app) # Enable CORS for all routes

# --- Initialize TTS Pipeline ---
try:
    print(f"Initializing Kokoro Pipeline for TTS Service with lang='{LANGUAGE_CODE}'...")
    pipeline = KPipeline(lang_code=LANGUAGE_CODE)
    print("TTS Service Pipeline initialized.")
except Exception as e:
    print(f"Error initializing Kokoro pipeline for TTS Service: {e}")
    pipeline = None

# --- API Endpoint for TTS ---
@app.route('/api/speak', methods=['POST'])
def speak_route_tts_service():
    if not pipeline:
        return jsonify({"error": "TTS Pipeline not initialized on TTS Service"}), 500

    data = request.json
    if not data or 'text' not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400
    
    text_to_speak = data.get("text", "").strip()

    if not text_to_speak:
        return jsonify({"error": "No text to speak"}), 400

    try:
        print(f"TTS Service: Generating audio for: {text_to_speak}")
        generator = pipeline(text_to_speak, voice=VOICE_MODEL)
        all_audio_chunks = []
        for i, (_, _, audio_chunk) in enumerate(generator):
            if audio_chunk is not None and len(audio_chunk) > 0:
                all_audio_chunks.append(audio_chunk)

        if all_audio_chunks:
            complete_audio = np.concatenate(all_audio_chunks)
            filename = f"speech_tts_service_{uuid.uuid4().hex}.wav"
            filepath = os.path.join(TTS_STATIC_FOLDER, filename)
            sf.write(filepath, complete_audio, SAMPLE_RATE)
            
            # Construct full URL. Since this might be on a different port,
            # the host_url is important.
            audio_url = request.host_url + f"{TTS_STATIC_FOLDER}/{filename}"
            print(f"TTS Service: Audio saved to {filepath}, URL: {audio_url}")
            return jsonify({"audio_url": audio_url, "text_spoken": text_to_speak})
        else:
            return jsonify({"error": "TTS generated no audio on TTS Service"}), 500
    except Exception as e:
        print(f"TTS Service: Error generating audio: {e}")
        return jsonify({"error": f"TTS Service: Error generating audio: {str(e)}"}), 500

# Serve static audio files for this TTS service
@app.route(f'/{TTS_STATIC_FOLDER}/<path:filename>')
def serve_static_audio_tts_service(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    # Run this TTS backend on a DIFFERENT PORT, e.g., 5001
    # And ensure use_reloader=False for testing stability
    print(f"TTS Service audio files will be served from local dir: {os.path.abspath(TTS_STATIC_FOLDER)}")
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False) 