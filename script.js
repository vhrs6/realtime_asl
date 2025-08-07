// script.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Global Config ---
    const BACKEND_URL = 'http://localhost:5000'; // Your ASL backend URL
    const TTS_BACKEND_URL = 'http://localhost:5001'; // Your SEPARATE TTS backend URL

    // --- Global Error Handlers ---
    window.addEventListener('unhandledrejection', function(event) {
        console.error('GLOBAL UNHANDLED PROMISE REJECTION:', event.reason);
        const outputElement = document.getElementById('translationOutput'); // Attempt to show on main page
        if (outputElement) {
            outputElement.textContent = `Unhandled Rejection: ${event.reason && event.reason.message ? event.reason.message : event.reason}`;
            outputElement.style.color = 'red';
        }
    });
    window.addEventListener('error', function(event) {
        console.error('GLOBAL ERROR EVENT:', event.message, 'at', event.filename, ':', event.lineno, event.error);
        const outputElement = document.getElementById('translationOutput'); // Attempt to show on main page
        if (outputElement) {
            outputElement.textContent = `Global Error: ${event.message}`;
            outputElement.style.color = 'red';
        }
    });
    // --- END OF GLOBAL HANDLERS ---

    // --- State Variables ---
    let videoStream = null;
    let videoElement = null;
    let canvasElement = null;
    let canvasCtx = null;
    let currentWordOnFrontend = "";
    let isAutoProcessing = false;
    let autoProcessIntervalId = null;

    // --- Helper: Update Word Display ---
    function updateWordDisplay() {
        const displayElement = document.getElementById('currentWordDisplay');
        if (displayElement) {
            displayElement.textContent = `Word: ${currentWordOnFrontend}`;
        }
    }

    // --- Helper: Show Messages ---
    function showDetectionMessage(message, isError = false) {
        const outputElement = document.getElementById('translationOutput');
        if (outputElement) {
            outputElement.textContent = message;
            outputElement.style.color = isError ? 'var(--primary-red, #ef4444)' : 'var(--text-light)';
        }
    }

    // --- Basic active link highlighter ---
    const navLinks = document.querySelectorAll('header nav ul li a');
    const currentPath = window.location.pathname.split('/').pop() || 'index.html';
    navLinks.forEach(link => {
        const linkPath = link.getAttribute('href').split('/').pop() || 'index.html';
        if (linkPath === currentPath) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    // --- Translator Page Specific Logic ---
    if (document.querySelector('.translator-interface')) {
        const translatorForm = document.getElementById('translatorForm'); // Assuming translator.html has this form wrapper
        if (translatorForm) {
            translatorForm.addEventListener('submit', (event) => {
                console.log('Translator form submit event caught and PREVENTED.');
                event.preventDefault();
            });
        }

        const startCameraButton = document.getElementById('startCameraButton');
        const videoPlaceholder = document.querySelector('.video-placeholder');
        const processSignButton = document.getElementById('processSignButton');
        const actionButtonsContainer = document.getElementById('actionButtonsContainer');
        // const audioPlayerContainer = document.getElementById('audioPlayerContainer'); // Not used for window.open

        // Ensure static buttons in HTML have type="button"
        if (startCameraButton) startCameraButton.setAttribute('type', 'button');
        if (processSignButton) processSignButton.setAttribute('type', 'button');


        videoElement = document.createElement('video');
        videoElement.setAttribute('autoplay', '');
        videoElement.setAttribute('playsinline', '');
        videoElement.style.width = '100%';
        videoElement.style.maxWidth = '640px';
        videoElement.style.height = 'auto';
        videoElement.style.display = 'none';
        videoElement.style.border = '1px solid var(--border-color)';
        videoElement.style.borderRadius = 'var(--border-radius-sm)';
        videoPlaceholder.appendChild(videoElement);

        canvasElement = document.createElement('canvas');
        canvasCtx = canvasElement.getContext('2d', { willReadFrequently: true });

        const btnAddLetter = document.createElement('button');
        btnAddLetter.setAttribute('type', 'button');
        btnAddLetter.textContent = 'Add Letter';
        btnAddLetter.classList.add('btn', 'btn-secondary');

        const btnAddSpace = document.createElement('button');
        btnAddSpace.setAttribute('type', 'button');
        btnAddSpace.textContent = 'Add Space';
        btnAddSpace.classList.add('btn', 'btn-secondary');

        const btnClear = document.createElement('button');
        btnClear.setAttribute('type', 'button');
        btnClear.textContent = 'Clear Word';
        btnClear.classList.add('btn', 'btn-secondary');

        const btnSpeak = document.createElement('button');
        btnSpeak.setAttribute('type', 'button');
        btnSpeak.textContent = 'Speak Word';
        btnSpeak.classList.add('btn', 'btn-primary');

        const btnToggleAutoProcess = document.createElement('button');
        btnToggleAutoProcess.setAttribute('type', 'button');
        btnToggleAutoProcess.textContent = 'Start Auto-Process';
        btnToggleAutoProcess.classList.add('btn', 'btn-secondary');
        btnToggleAutoProcess.title = "Automatically process sign every 2 seconds";

        actionButtonsContainer.appendChild(btnAddLetter);
        actionButtonsContainer.appendChild(btnAddSpace);
        actionButtonsContainer.appendChild(btnClear);
        actionButtonsContainer.appendChild(btnSpeak);
        actionButtonsContainer.appendChild(btnToggleAutoProcess);

        if (startCameraButton) {
            startCameraButton.addEventListener('click', async (event) => {
                event.preventDefault();
                event.stopPropagation();
                try {
                    if (videoStream) {
                        videoStream.getTracks().forEach(track => track.stop());
                    }
                    videoStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
                    videoElement.srcObject = videoStream;
                    await videoElement.play();
                    videoElement.style.display = 'block';
                    startCameraButton.textContent = 'Restart Camera'; // Changed from 'Switch Camera'
                    startCameraButton.classList.replace('btn-primary', 'btn-secondary');
                    if (videoPlaceholder.querySelector('p')) videoPlaceholder.querySelector('p').style.display = 'none';
                    showDetectionMessage('Camera active. Position your hand and process the sign.');
                } catch (err) {
                    console.error("Error accessing camera: ", err);
                    showDetectionMessage(`Error accessing camera: ${err.message}. Please check permissions.`, true);
                }
            });
        }

        async function processCurrentFrameAPI() {
            if (!videoStream || videoElement.paused || videoElement.ended || videoElement.videoWidth === 0) {
                showDetectionMessage('Camera not ready or no frame to process.', true);
                return;
            }
            canvasElement.width = videoElement.videoWidth;
            canvasElement.height = videoElement.videoHeight;
            canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
            canvasCtx.save();
            canvasCtx.scale(-1, 1);
            canvasCtx.drawImage(videoElement, -canvasElement.width, 0, canvasElement.width, canvasElement.height);
            canvasCtx.restore();
            const imageData = canvasElement.toDataURL('image/jpeg', 0.8);
            try {
                showDetectionMessage('Processing sign...');
                const response = await fetch(`${BACKEND_URL}/api/process_frame`, { // Points to ASL backend
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_data: imageData })
                });
                if (!response.ok) {
                    const errData = await response.json().catch(() => ({ error: "Unknown error from ASL backend." }));
                    throw new Error(errData.error || `HTTP error from ASL backend! Status: ${response.status}`);
                }
                const result = await response.json();
                if (result.char) {
                    showDetectionMessage(`Detected: ${result.char} (Confidence: ${result.confidence.toFixed(2)})`);
                } else if (result.message) {
                    showDetectionMessage(`${result.message} (Confidence: ${result.confidence.toFixed(2)})`);
                } else {
                    showDetectionMessage("Detection unclear or no hand found.");
                }
            } catch (error) {
                console.error('Error processing frame:', error);
                showDetectionMessage(`Frame Process Error: ${error.message}`, true);
            }
        }

        if (processSignButton) {
            processSignButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                processCurrentFrameAPI();
            });
        }

        btnToggleAutoProcess.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!videoStream) {
                showDetectionMessage("Please start the camera first.", true);
                return;
            }
            isAutoProcessing = !isAutoProcessing;
            if (isAutoProcessing) {
                btnToggleAutoProcess.textContent = 'Stop Auto-Process';
                btnToggleAutoProcess.classList.replace('btn-secondary', 'btn-primary');
                processCurrentFrameAPI();
                autoProcessIntervalId = setInterval(processCurrentFrameAPI, 2000);
                showDetectionMessage("Auto-processing started (every 2 seconds).");
            } else {
                btnToggleAutoProcess.textContent = 'Start Auto-Process';
                btnToggleAutoProcess.classList.replace('btn-primary', 'btn-secondary');
                clearInterval(autoProcessIntervalId);
                showDetectionMessage("Auto-processing stopped.");
            }
        });

        btnAddLetter.addEventListener('click', async (event) => {
            event.preventDefault();
            event.stopPropagation();
            try {
                const response = await fetch(`${BACKEND_URL}/api/add_char`, { // Points to ASL backend
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const result = await response.json();
                if (result.added) {
                    currentWordOnFrontend = result.current_word;
                    updateWordDisplay();
                    showDetectionMessage(`Letter '${result.added}' added to word.`);
                } else {
                    showDetectionMessage("No recent character detected to add.", true);
                }
            } catch (error) {
                console.error('Error adding letter:', error);
                showDetectionMessage(`Add Letter Error: ${error.message}`, true);
            }
        });

        btnAddSpace.addEventListener('click', async (event) => {
            event.preventDefault();
            event.stopPropagation();
             try {
                const response = await fetch(`${BACKEND_URL}/api/add_space`, { method: 'POST' }); // Points to ASL backend
                const result = await response.json();
                currentWordOnFrontend = result.current_word;
                updateWordDisplay();
                showDetectionMessage("Space added.");
            } catch (error) {
                console.error('Error adding space:', error);
                showDetectionMessage(`Add Space Error: ${error.message}`, true);
            }
        });

        btnClear.addEventListener('click', async (event) => {
            event.preventDefault();
            event.stopPropagation();
            try {
                const response = await fetch(`${BACKEND_URL}/api/clear_word`, { method: 'POST' }); // Points to ASL backend
                const result = await response.json();
                currentWordOnFrontend = result.current_word;
                updateWordDisplay();
                const audioPlayerContainer = document.getElementById('audioPlayerContainer');
                if (audioPlayerContainer) audioPlayerContainer.innerHTML = ''; // Clear audio player if it existed
                showDetectionMessage("Word cleared. Last detection also cleared.");
            } catch (error) {
                console.error('Error clearing word:', error);
                showDetectionMessage(`Clear Word Error: ${error.message}`, true);
            }
        });

        // --- WORKAROUND 1: Open audio in new tab (using SEPARATE TTS_BACKEND_URL) ---
        btnSpeak.addEventListener('click', async (event) => { 
            console.log('Speak button clicked (Workaround: New Tab). Timestamp:', Date.now());
            event.preventDefault();
            event.stopPropagation();

            const textToSpeak = currentWordOnFrontend.trim();
            if (!textToSpeak) {
                showDetectionMessage("Nothing to speak yet. Add letters to the word.", true);
                return;
            }

            showDetectionMessage(`Requesting audio for: "${textToSpeak}" from TTS Service...`);
            
            try {
                const response = await fetch(`${TTS_BACKEND_URL}/api/speak`, { // Points to TTS backend
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: textToSpeak })
                });

                console.log('Fetch to TTS Service /api/speak completed. Status:', response.status);

                if (!response.ok) {
                    const errText = await response.text().catch(() => "Failed to get error text from TTS service.");
                    console.error(`TTS Service Error: Status ${response.status}, Body: ${errText}`);
                    throw new Error(`TTS Service error! Status: ${response.status}. ${errText}`);
                }

                const result = await response.json();
                console.log('Received result from TTS Service:', result);

                if (result && result.audio_url) {
                    // The audio_url from tts_backend.py is request.host_url + f"{TTS_STATIC_FOLDER}/{filename}"
                    // which should be a full URL like http://localhost:5001/static_audio_tts_service/speech....wav
                    showDetectionMessage(`Audio ready for "${result.text_spoken}". Opening in new tab...`);
                    window.open(result.audio_url, '_blank'); 
                    console.log('Opened audio URL in new tab:', result.audio_url);
                } else {
                    showDetectionMessage("TTS Backend did not return an audio URL.", true);
                    console.log('Result from TTS backend (no audio_url or unexpected):', result);
                }

            } catch (error) {
                console.error('Error in Speak (New Tab) handler:', error);
                showDetectionMessage(`Speak Error: ${error.message}`, true);
            }
            console.log('End of Speak (New Tab) handler. Timestamp:', Date.now());
        });
        // --- END OF WORKAROUND 1 ---

        updateWordDisplay(); // Initial display
    }
});