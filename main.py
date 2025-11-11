# main.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool # Added for async os.remove
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import time
from openai import AsyncOpenAI # Changed to AsyncOpenAI
from dotenv import load_dotenv
import uuid
import aiofiles # Added for async file operations

load_dotenv()
api_key = os.getenv("openai_api_key")
# Use the AsyncOpenAI client for non-blocking API calls
client = AsyncOpenAI(api_key=api_key)

app = FastAPI(title="Dr. HealBot API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def serve_home():
    return FileResponse("index.html")

# Serve CSS
@app.get("/style.css")
def serve_css():
    return FileResponse("style.css")

# Serve JS
@app.get("/script.js")
def serve_js():
    return FileResponse("script.js")
# =====================================================
# DOCTOR SYSTEM PROMPT
# =====================================================
DOCTOR_SYSTEM_PROMPT = """
You are Dr. HealBot, a calm, knowledgeable, and empathetic virtual doctor.

GOAL:
Hold a natural, focused conversation with the patient to understand their health issue and offer helpful preliminary medical guidance.

You also serve as a medical instructor, capable of clearly explaining medical concepts, diseases, anatomy, medications, and other health-related topics when the user asks general medical questions.

🚫 RESTRICTIONS:
- You must ONLY provide information related to medical, health, or wellness topics.
- If the user asks anything non-medical (e.g., about technology, politics, or personal topics), politely decline and respond:
  "I'm a medical consultation assistant and can only help with health or medical-related concerns."
- Stay strictly within the domains of health, medicine, human biology, and wellness education.

CONVERSATION LOGIC:
- Ask only relevant and concise medical questions necessary for diagnosing the illness.
- Each question should help clarify symptoms or narrow possible causes.
- Stop asking once enough information is collected for a basic assessment.
- Then, provide a structured, friendly, and visually clear medical response using headings, emojis, and bullet points.

- Automatically detect if the user is asking a **general medical question** (e.g., "What is diabetes?", "How does blood pressure work?", "Explain antibiotics").
    - In such cases, switch to **Instructor Mode**:
        - Give a clear, educational, and structured explanation.
        - Use short paragraphs or bullet points.
        - Maintain a professional but approachable tone.
        - Conclude with a brief practical takeaway or health tip if appropriate.
- If the user is describing symptoms or a health issue, continue in **Doctor Mode**:

FINAL RESPONSE FORMAT:
When giving your full assessment, use this markdown-styled format:

🩺 Based on what you've told me...
Brief summary of what the patient described.

💡 Possible Causes (Preliminary)
- List 1–2 possible conditions using phrases like "It could be" or "This sounds like".
- Include a disclaimer that this is not a confirmed diagnosis.

🥗 Lifestyle & Home Care Tips
- 2–3 practical suggestions (rest, hydration, warm compress, balanced diet, etc.)

⚠️ When to See a Real Doctor
- 2–3 warning signs or conditions when urgent medical care is needed.

📅 Follow-Up Advice
- Brief recommendation for self-care or follow-up timing (e.g., "If not improving in 3 days, visit a clinic.")

TONE & STYLE:
- Speak like a real, caring doctor – short, clear, and empathetic (1–2 sentences per reply).
- Use plain language, no jargon.
- Only one question per turn unless clarification is essential.
- Keep tone warm, calm, and professional.
- Early messages: short questions only.
- Final message: structured output with emojis and headings.

IMPORTANT:
- Never provide any information outside medical context.
- Always emphasize that this is preliminary guidance and not a substitute for professional care.
- Never make definitive diagnoses; use phrases like "it sounds like" or "it could be".
- If symptoms seem serious, always recommend urgent medical attention.
"""

# =====================================================
# SESSION MANAGEMENT
# =====================================================
SESSIONS_DIR = "sessions"
AUDIO_DIR = "audio_files"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# In-memory session storage (use Redis in production)
sessions = {}

# =====================================================
# MODELS
# =====================================================
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class SessionResponse(BaseModel):
    session_id: str
    messages: List[Message]

class ChatResponse(BaseModel):
    session_id: str
    response: str
    audio_url: Optional[str] = None
    transcript: Optional[str] = None  # Added for voice input

# =====================================================
# HELPER FUNCTIONS
# =====================================================
async def get_answer(messages):
    """Get AI response from OpenAI - Now non-blocking"""
    try:
        # Use await with the async client
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

async def speech_to_text(audio_path: str) -> dict:
    """Convert speech to text and return transcript + confidence estimate - Now non-blocking"""
    try:
        with open(audio_path, "rb") as audio_file:
            result = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json"
            )

        # Access as attributes, not dictionary keys
        transcript = result.text if result.text else ""

        # Estimate average confidence from segments
        segments = result.segments if hasattr(result, 'segments') and result.segments else []
        if segments:
            avg_confidence = sum(s.confidence if hasattr(s, 'confidence') else 1.0 for s in segments) / len(segments)
        else:
            avg_confidence = 1.0  # Default to high confidence if no segments

        return {"text": transcript, "confidence": avg_confidence}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Speech-to-text error: {str(e)}")


async def text_to_speech(input_text):
    """Convert text to speech using OpenAI TTS - Now non-blocking"""
    try:
        # Use await with the async client
        response = await client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=input_text
        )
        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        
        # Use the async 'astream_to_file' method
        await response.astream_to_file(audio_path)
        
        return audio_filename
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text-to-speech error: {str(e)}")

def create_new_session():
    """Create a new chat session"""
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "messages": [
            {"role": "system", "content": DOCTOR_SYSTEM_PROMPT},
            {"role": "assistant", "content": "👋 Hello! I'm Dr. HealBot. How can I help you with your health today?"}
        ],
        "created_at": time.time()
    }
    return session_id

async def save_session_to_file(session_id):
    """Save session to JSON file - Now non-blocking"""
    if session_id in sessions:
        timestamp = int(time.time())
        filename = os.path.join(SESSIONS_DIR, f"session_{session_id}_{timestamp}.json")
        
        # Use aiofiles for async file writing
        async with aiofiles.open(filename, "w") as f:
            await f.write(json.dumps(sessions[session_id]["messages"], indent=2))

# =====================================================
# API ENDPOINTS
# =====================================================
@app.get("/")
async def root():
    return {"message": "Dr. HealBot API is running", "version": "1.0"}

@app.post("/session/new", response_model=SessionResponse)
async def new_session():
    """Create a new chat session"""
    session_id = create_new_session()
    return {
        "session_id": session_id,
        "messages": sessions[session_id]["messages"]
    }

@app.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session messages"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "messages": sessions[session_id]["messages"]
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get AI response"""
    if not request.session_id or request.session_id not in sessions:
        session_id = create_new_session()
    else:
        session_id = request.session_id
    
    sessions[session_id]["messages"].append({
        "role": "user",
        "content": request.message
    })
    
    # Use await for the async helper
    ai_response = await get_answer(sessions[session_id]["messages"])
    
    sessions[session_id]["messages"].append({
        "role": "assistant",
        "content": ai_response
    })
    
    # Use await for the async helper
    audio_filename = await text_to_speech(ai_response)
    
    return {
        "session_id": session_id,
        "response": ai_response,
        "audio_url": f"/audio/{audio_filename}"
    }

@app.post("/chat/voice", response_model=ChatResponse)
async def chat_voice(session_id: Optional[str] = Form(None), audio: UploadFile = File(...)):
    """Send voice message and get AI response - Now fully async"""

    if not session_id or session_id not in sessions:
        session_id = create_new_session()

    # Save uploaded audio asynchronously
    audio_path = os.path.join(AUDIO_DIR, f"temp_{uuid.uuid4()}.mp3")
    async with aiofiles.open(audio_path, "wb") as f:
        await f.write(await audio.read())

    # Transcribe (async)
    result = await speech_to_text(audio_path)
    transcript = result["text"].strip()
    confidence = result["confidence"]

    # Remove temp file (non-blocking)
    await run_in_threadpool(os.remove, audio_path)

    # 🔹 Confidence-based check
    if not transcript or confidence < 0.7:
        # This is a valid response, not an error
        response_text = "I'm sorry, I couldn't clearly understand your voice message. Could you please repeat it slowly?"
        
        # Also generate audio for this "I didn't understand" message
        audio_filename = await text_to_speech(response_text)
        
        return ChatResponse(
            session_id=session_id,
            response=response_text,
            audio_url=f"/audio/{audio_filename}",
            transcript=transcript or "[unclear speech]"
        )

    # Add user message
    sessions[session_id]["messages"].append({
        "role": "user",
        "content": transcript
    })

    # Get AI response (async)
    ai_response = await get_answer(sessions[session_id]["messages"])

    # Add assistant message
    sessions[session_id]["messages"].append({
        "role": "assistant",
        "content": ai_response
    })

    # Generate audio response (async)
    audio_filename = await text_to_speech(ai_response)

    return ChatResponse(
        session_id=session_id,
        response=ai_response,
        audio_url=f"/audio/{audio_filename}",
        transcript=transcript
    )

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve audio file - NOW SECURE"""
    audio_path = os.path.join(AUDIO_DIR, filename)

    # === SECURITY FIX: Prevent Path Traversal ===
    # Get the absolute paths
    abs_audio_dir = os.path.abspath(AUDIO_DIR)
    abs_audio_path = os.path.abspath(audio_path)

    # Check if the resolved file path is still inside the intended directory
    # and if the file actually exists.
    if not abs_audio_path.startswith(abs_audio_dir) or not os.path.exists(abs_audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found or invalid path")
    
    return FileResponse(abs_audio_path, media_type="audio/mpeg")

@app.post("/session/{session_id}/save")
async def save_session(session_id: str):
    """Save session to file - Now async"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await save_session_to_file(session_id)
    return {"message": "Session saved successfully"}

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session from in-memory store"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]
    return {"message": "Session deleted successfully"}

@app.get("/sessions")
async def list_sessions():
    """List all saved session files - Now async"""
    # Use run_in_threadpool for blocking I/O (os.listdir)
    files = await run_in_threadpool(os.listdir, SESSIONS_DIR)
    files.sort(reverse=True)
    return {"sessions": files}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

