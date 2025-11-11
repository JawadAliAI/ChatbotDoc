const chatbotToggler = document.querySelector(".chatbot-toggler");
const closeBtn = document.querySelector(".close-btn");
const chatbox = document.querySelector(".chatbox");
const chatInput = document.querySelector(".chat-input textarea");
const sendChatBtn = document.querySelector(".chat-input span");
const voiceBtn = document.querySelector("#voice-btn");
const recordingIndicator = document.querySelector(".recording-indicator");
const responseAudio = document.querySelector("#response-audio");

// Patient Modal Elements
const patientModal = document.getElementById("patient-modal");
const patientNameInput = document.getElementById("patient-name-input");
const startNewBtn = document.getElementById("start-new-btn");
const loadSessionBtn = document.getElementById("load-session-btn");
const patientNameDisplay = document.getElementById("patient-name-display");

let userMessage = null;
const inputInitHeight = chatInput.scrollHeight;

// API configuration - Update this to your FastAPI backend URL
const API_BASE_URL = "http://localhost:8000";

// Session management
let sessionId = null;
let currentPatientName = null;

// Voice recording variables
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// =====================================================
// PATIENT MODAL MANAGEMENT
// =====================================================

// Show modal on page load
const showPatientModal = () => {
  patientModal.classList.remove("hidden");
  console.log("Modal shown");
};

// Hide modal
const hidePatientModal = () => {
  patientModal.classList.add("hidden");
  console.log("Modal hidden");
};

// Check if user has a saved name
const checkSavedPatient = () => {
  const savedName = localStorage.getItem("patientName");
  if (savedName) {
    patientNameInput.value = savedName;
    console.log("Loaded saved patient name:", savedName);
  }
};

// Initialize session
const initializeSession = async () => {
  try {
    console.log("Initializing new session...");
    const response = await fetch(`${API_BASE_URL}/session/new`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    sessionId = data.session_id;
    console.log("Session initialized:", sessionId);
    
    // Save session ID for current patient
    if (currentPatientName) {
      localStorage.setItem(`session_${currentPatientName}`, sessionId);
      console.log("Session saved for patient:", currentPatientName);
    }
    
    return sessionId;
  } catch (error) {
    console.error("Failed to initialize session:", error);
    alert("Failed to connect to server. Please check if the backend is running on http://localhost:8000");
    throw error;
  }
};

// Start new session button handler
startNewBtn.addEventListener("click", async () => {
  console.log("Start New Session clicked");
  const name = patientNameInput.value.trim();
  
  if (!name) {
    alert("Please enter your name to continue.");
    return;
  }
  
  console.log("Starting new session for:", name);
  currentPatientName = name;
  patientNameDisplay.textContent = name;
  
  try {
    // Initialize new session
    await initializeSession();
    
    // Clear chatbox and add welcome message
    chatbox.innerHTML = `
      <li class="chat incoming">
        <span class="material-symbols-outlined">smart_toy</span>
        <p>👋 Hello ${name}! I'm Dr. HealBot. How can I help you with your health today?</p>
      </li>
    `;
    
    hidePatientModal();
    
    // Save patient name to localStorage
    localStorage.setItem("patientName", name);
    console.log("New session started successfully");
  } catch (error) {
    console.error("Error starting new session:", error);
  }
});

// Load previous session button handler
loadSessionBtn.addEventListener("click", async () => {
  console.log("Load Previous Session clicked");
  const name = patientNameInput.value.trim();
  
  if (!name) {
    alert("Please enter your name to continue.");
    return;
  }
  
  console.log("Loading session for:", name);
  currentPatientName = name;
  patientNameDisplay.textContent = name;
  
  // Try to load existing session
  const savedSessionId = localStorage.getItem(`session_${name}`);
  console.log("Saved session ID:", savedSessionId);
  
  if (savedSessionId) {
    try {
      const response = await fetch(`${API_BASE_URL}/session/${savedSessionId}`);
      if (response.ok) {
        const data = await response.json();
        sessionId = data.session_id;
        console.log("Session loaded:", sessionId);
        
        // Restore chat history
        chatbox.innerHTML = "";
        data.messages.forEach(msg => {
          if (msg.role === "assistant") {
            const li = createChatLi(msg.content, "incoming");
            chatbox.appendChild(li);
          } else if (msg.role === "user") {
            const li = createChatLi(msg.content, "outgoing");
            chatbox.appendChild(li);
          }
        });
        
        chatbox.scrollTo(0, chatbox.scrollHeight);
        hidePatientModal();
        localStorage.setItem("patientName", name);
        console.log("Previous session restored successfully");
        return;
      }
    } catch (error) {
      console.log("No previous session found, starting new one:", error);
    }
  }
  
  // If no session found, start new one
  try {
    await initializeSession();
    chatbox.innerHTML = `
      <li class="chat incoming">
        <span class="material-symbols-outlined">smart_toy</span>
        <p>👋 Welcome back ${name}! I'm Dr. HealBot. How can I help you with your health today?</p>
      </li>
    `;
    
    hidePatientModal();
    localStorage.setItem("patientName", name);
    console.log("New session started for returning patient");
  } catch (error) {
    console.error("Error loading session:", error);
  }
});

// =====================================================
// CHAT FUNCTIONS
// =====================================================

// Create chat message element
const createChatLi = (message, className, isVoice = false) => {
  const chatLi = document.createElement("li");
  chatLi.classList.add("chat", `${className}`);
  let chatContent = className === "outgoing" 
    ? `<p></p>` 
    : `<span class="material-symbols-outlined">smart_toy</span><p></p>`;
  chatLi.innerHTML = chatContent;
  const paragraph = chatLi.querySelector("p");
  paragraph.textContent = message;
  if (isVoice && className === "outgoing") {
    paragraph.classList.add("voice-message");
  }
  return chatLi;
};

// Send text message to API
const sendTextMessage = async (message) => {
  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message: message,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    sessionId = data.session_id; // Update session ID
    
    return {
      response: data.response,
      audioUrl: data.audio_url,
    };
  } catch (error) {
    throw new Error(`Failed to send message: ${error.message}`);
  }
};

// Send voice message to API
const sendVoiceMessage = async (audioBlob) => {
  try {
    const formData = new FormData();
    formData.append("audio", audioBlob, "voice.mp3");
    if (sessionId) {
      formData.append("session_id", sessionId);
    }

    const response = await fetch(`${API_BASE_URL}/chat/voice`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    sessionId = data.session_id; // Update session ID
    
    return {
      response: data.response,
      audioUrl: data.audio_url,
      transcript: data.transcript,
    };
  } catch (error) {
    throw new Error(`Failed to send voice message: ${error.message}`);
  }
};

// Play audio response
const playAudioResponse = (audioUrl) => {
  if (audioUrl) {
    responseAudio.src = `${API_BASE_URL}${audioUrl}`;
    responseAudio.play().catch(error => {
      console.error("Error playing audio:", error);
    });
  }
};

// Generate text response
const generateResponse = async (chatElement, message) => {
  const messageElement = chatElement.querySelector("p");

  try {
    const data = await sendTextMessage(message);
    
    // Update message with response
    messageElement.textContent = data.response;
    messageElement.classList.remove("thinking");
    
    // Play audio response
    playAudioResponse(data.audioUrl);
    
  } catch (error) {
    messageElement.classList.add("error");
    messageElement.classList.remove("thinking");
    messageElement.textContent = error.message;
  } finally {
    chatbox.scrollTo(0, chatbox.scrollHeight);
  }
};

// Handle text chat
const handleChat = () => {
  userMessage = chatInput.value.trim();
  if (!userMessage) return;

  // Clear input
  chatInput.value = "";
  chatInput.style.height = `${inputInitHeight}px`;

  // Append user's message
  chatbox.appendChild(createChatLi(userMessage, "outgoing"));
  chatbox.scrollTo(0, chatbox.scrollHeight);

  setTimeout(() => {
    // Display "Thinking..." message
    const incomingChatLi = createChatLi("Thinking...", "incoming");
    incomingChatLi.querySelector("p").classList.add("thinking");
    chatbox.appendChild(incomingChatLi);
    chatbox.scrollTo(0, chatbox.scrollHeight);
    generateResponse(incomingChatLi, userMessage);
  }, 600);
};

// =====================================================
// VOICE RECORDING FUNCTIONS
// =====================================================

const startRecording = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: "audio/mp3" });
      await handleVoiceMessage(audioBlob);
      
      // Stop all tracks
      stream.getTracks().forEach(track => track.stop());
    };

    mediaRecorder.start();
    isRecording = true;
    voiceBtn.classList.add("recording");
    recordingIndicator.style.display = "flex";
    console.log("Recording started");
    
  } catch (error) {
    console.error("Error accessing microphone:", error);
    alert("Unable to access microphone. Please check permissions.");
  }
};

const stopRecording = () => {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    voiceBtn.classList.remove("recording");
    recordingIndicator.style.display = "none";
    console.log("Recording stopped");
  }
};

// Handle voice message
const handleVoiceMessage = async (audioBlob) => {
  // Show processing message
  const processingLi = createChatLi("Processing voice message...", "outgoing", true);
  chatbox.appendChild(processingLi);
  chatbox.scrollTo(0, chatbox.scrollHeight);

  try {
    const data = await sendVoiceMessage(audioBlob);
    
    // Update user message with transcript
    const userMessageElement = processingLi.querySelector("p");
    userMessageElement.textContent = data.transcript || "[Voice message]";
    
    // Add bot response
    setTimeout(() => {
      const incomingChatLi = createChatLi(data.response, "incoming");
      chatbox.appendChild(incomingChatLi);
      chatbox.scrollTo(0, chatbox.scrollHeight);
      
      // Play audio response
      playAudioResponse(data.audioUrl);
    }, 300);
    
  } catch (error) {
    const errorLi = createChatLi(`Error: ${error.message}`, "incoming");
    errorLi.querySelector("p").classList.add("error");
    chatbox.appendChild(errorLi);
    chatbox.scrollTo(0, chatbox.scrollHeight);
  }
};

// =====================================================
// EVENT LISTENERS
// =====================================================

chatInput.addEventListener("input", () => {
  chatInput.style.height = `${inputInitHeight}px`;
  chatInput.style.height = `${chatInput.scrollHeight}px`;
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && window.innerWidth > 800) {
    e.preventDefault();
    handleChat();
  }
});

sendChatBtn.addEventListener("click", handleChat);

// Voice button - toggle recording
voiceBtn.addEventListener("click", () => {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
});

closeBtn.addEventListener("click", () => {
  document.body.classList.remove("show-chatbot");
  // Stop recording if active
  if (isRecording) {
    stopRecording();
  }
});

chatbotToggler.addEventListener("click", () => {
  document.body.classList.toggle("show-chatbot");
});

// =====================================================
// INITIALIZE ON PAGE LOAD
// =====================================================

console.log("Script loaded");
checkSavedPatient();
showPatientModal();