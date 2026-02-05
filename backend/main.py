from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from collections import deque
from config import KEYWORD_MAPPING
import json
from datetime import datetime
import logging
import random
import time
import tempfile
import os

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

# ---------- OpenAI ----------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Exhibit Feedback Chatbot API",
    version="1.4.0",
    description="Full Backend: Unified Chat Logic + STT/TTS + Global Context",
)

#============ LOAD EXHIBIT QUESTIONS ============
QUESTIONS_PATH = os.getenv("EXHIBIT_QUESTIONS_PATH", "data/exhibit_questions.json")
FEEDBACK_LOG_PATH = os.getenv("FEEDBACK_LOG_PATH", "data/feedback_log.jsonl")

EXHIBIT_QUESTIONS: Dict[str, Any] = {}
GLOBAL_KB_STR: str = ""  # Stores the full text description of the museum

def load_exhibit_questions():
    global EXHIBIT_QUESTIONS, GLOBAL_KB_STR
    try:
        with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
            EXHIBIT_QUESTIONS = json.load(f)
        
        # === NEW: Build Knowledge Base for the LLM ===
        # This helps the bot know what "Faces" or "Sandbox" actually is.
        kb_lines = []
        for name, data in EXHIBIT_QUESTIONS.items():
            desc = data.get("one_liner", "An interactive display.")
            kb_lines.append(f"- {name}: {desc}")
        GLOBAL_KB_STR = "\n".join(kb_lines)
        
        logger.info(f"Loaded exhibit questions: {len(EXHIBIT_QUESTIONS)} exhibits")
    except Exception as e:
        EXHIBIT_QUESTIONS = {}
        GLOBAL_KB_STR = ""
        logger.warning(f"Using empty question bank. Error: {e}")

def log_feedback_event(event: Dict[str, Any]):
    try:
        os.makedirs(os.path.dirname(FEEDBACK_LOG_PATH), exist_ok=True)
        event["ts"] = datetime.now().isoformat()
        with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Log failed: {e}")

# ============ CONFIGURATION ============
MAX_USER_TURNS = int(os.getenv("MAX_USER_TURNS", "5")) 
MAX_OUTPUT_TOKENS = 150

EXHIBITS = [
    "D4A","Asan.AI","Swarming bacteria","Chatbot","Circuit Flowfields",
    "Complex calculations","Complexity Explorables","Data traces","Dresden mapping",
    "Faces","Film Forms","Hyperuniformity","Magic Mirror","Mathematical models",
    "Physarum","Retro Reboot","Sandbox","Seamless pattern","Server cabinet",
    "Server kit","Time travel","Traces","VR experience"
]

# Smart Keyword Mapping (The Fix)

# ============ UNIFIED PROMPT GENERATOR (THE LOGIC FIX) ============
def build_unified_system_prompt(
    target_question: str, 
    current_exhibit: str, 
    one_liner: str, 
    is_closing: bool = False,
    transition_note: Optional[str] = None  # <--- NEW ARGUMENT
) -> str:
    
    # 1. Base Persona
    prompt = f"""
You are the embodied subconscious of the 'Data Spaces' exhibition. 
Your goal is to collect specific feedback from the visitor.

Global Exhibition Knowledge (Use this to answer factual questions):
{GLOBAL_KB_STR}

Context:
- Current Topic: {current_exhibit if current_exhibit else "General (No exhibit selected)"}
"""

    # 2. CLOSING LOGIC
    if is_closing:
        prompt += """
Current Status: CONVERSATION ENDING.
Task:
1. Review the conversation history.
2. Generate a 2-sentence closing.
   - If they gave feedback, summarize it ("Thanks for your thoughts on the VR").
   - If not, just say thanks.
3. End politely. Do NOT ask any new questions.
"""
        return prompt

    # 3. INTERVIEW LOGIC (STRICTER NOW)
    prompt += f"""
Current Status: ACTIVE INTERVIEW.

Your Mandatory Goal:
You MUST get an answer to this specific question: 
>>> "{target_question}"

INSTRUCTIONS:
1. **Answer First:** If the user asked a question (e.g., "How does it work?"), answer it clearly using the 'Global Exhibition Knowledge' above.
2. **Transition Immediately:** After answering, you MUST asks the Target Question above.
3. **Negative Constraints:** - Do NOT ask "Do you want to know more?"
   - Do NOT ask "Is there anything else?"
   - Do NOT ask "Does that make sense?"
   - ONLY ask the Target Question.

Example Interaction:
User: "What is Faces?"
You: "Faces uses LiDAR sensors to track your eyes. Did seeing that feel playful or creepy?" 
(Notice how you answered, then immediately pivoted to the feedback question).
"""
    
    # === NEW: Inject the Transition Instruction ===
    if transition_note:
        prompt += f"\n**SPECIAL TRANSITION:** {transition_note}\n"
    # ==============================================

    return prompt

def call_llm(system_prompt: str, history: List[Dict[str, str]]) -> str:
    messages = [{"role": "system", "content": system_prompt}] + history
    try:
        resp = client.responses.create(
            model=MODEL,
            input=messages,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.7 
        )
        return (resp.output_text or "").strip()
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return "I'm having trouble connecting to my memory. What did you say?"

# ============ SESSION MANAGEMENT ============
SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def _get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {
            "messages": [],
            "selected_exhibit": None,
            "asked_qids": set(),
            "last_qid": None,
            "turn_count": 0,
            "selection_attempts": 0  # <--- NEW: Initialize counter
        }
    return SESSION_STORE[session_id]

def _append_message(session_id: str, role: str, content: str):
    s = _get_session(session_id)
    # Memory Window: Keep last 10 messages
    if len(s["messages"]) >= 10:
        s["messages"].pop(0)
    s["messages"].append({"role": role, "content": content})

def detect_exhibit_from_text(text: str) -> Optional[str]:
    t = (text or "").lower()
    # 1. Check loaded JSON keys (Best source)
    for name in EXHIBIT_QUESTIONS.keys():
        if name.lower() in t: return name
    # 2. Check simple list (Fallback)
    for name in EXHIBITS:
        if name.lower() in t: return name
    # 3. Check Smart Keywords (The Fix)
    for keyword, official_name in KEYWORD_MAPPING.items():
        if keyword in t:
            return official_name
    return None

def get_next_question_logic(session: Dict[str, Any]) -> Dict[str, Any]:
    exhibit = session.get("selected_exhibit")
    
    # CASE 1: No exhibit selected
    if not exhibit:
        # === EXCEPTION: User explicitly asked to choose manually ===
        if session.get("force_open_choice"):
            session["force_open_choice"] = False  # Reset flag immediately (one-time use)
            # We do NOT increment "selection_attempts" because this is a valid request.
            return {
                "id": "select_exhibit_explicit",
                "text": "Understood. Which specific exhibit would you like to discuss? (e.g. Faces, VR, Sandbox)",
                "one_liner": "The user wants to select an exhibit manually.",
                "end_conversation": False
            }
        # ===========================================================

        # Standard Failure Logic (The Counter)
        session["selection_attempts"] = session.get("selection_attempts", 0) + 1
        attempts = session["selection_attempts"]

        # Attempts 1 & 2: Push the LiDAR Suggestions
        if attempts <= 2:
            suggestions = get_lidar_suggestions() 
            return {
                "id": "select_exhibit_lidar",
                "text": f"Hey, I noticed you spent the most time at the {suggestions}. Would you like to review one of them?",
                "one_liner": "I have access to visitor tracking data to see where you spent your time.",
                "end_conversation": False
            }
        
        # Attempt 3: Generic "Last Chance"
        elif attempts == 3:
            return {
                "id": "select_exhibit_generic",
                "text": "It seems I'm having trouble matching that to an exhibit. Would you like to give a review for ANY exhibit? If so, just say the name.",
                "one_liner": "I am trying to help the user start a review.",
                "end_conversation": False
            }
            
        # Attempt 4: Polite Exit (Graceful Failure)
        else:
             return {
                "id": "force_end",
                "text": "It looks like you might be done for now. Thank you for visiting Data Spaces!",
                "one_liner": "The user is not engaging. End the conversation politely.",
                "end_conversation": True
            }

    # CASE 2: Overall
    if exhibit == "overall exhibition":
        if "overall_improve" not in session["asked_qids"]:
            return {
                "id": "overall_improve",
                "text": "If you could change one thing about the whole exhibition, what would it be?",
                "one_liner": "This is Data Spaces.",
                "end_conversation": False
            }
        else:
            session["selected_exhibit"] = None 
            return {
                "id": "ask_restart",
                "text": "Would you like to review another exhibit? If yes, tell me which one.",
                "one_liner": None,
                "end_conversation": False
            }

    # CASE 3: Standard Pack
    pack = EXHIBIT_QUESTIONS.get(exhibit, {})
    # Default one-liner if missing from JSON
    one_liner = pack.get("one_liner", f"The {exhibit} is an interactive installation.") 
    questions = pack.get("questions", [])

    for q in questions:
        if q["id"] not in session["asked_qids"]:
            return {
                "id": q["id"],
                "text": q["text"],
                "one_liner": one_liner,
                "end_conversation": False
            }

    # CASE 4: No questions left
    session["selected_exhibit"] = None 
    return {
        "id": "ask_restart",
        "text": "That is all for this exhibit. Would you like to review another one?",
        "one_liner": one_liner,
        "end_conversation": False
    }

def get_lidar_suggestions() -> str:
    """
    Simulates fetching the 'Top 3 Visited Exhibits' from the LiDAR backend.
    """
    # 1. Try to read from a real file (Future Proofing)
    lidar_path = "data/lidar_stats.json" 
    if os.path.exists(lidar_path):
        try:
            with open(lidar_path, "r") as f:
                data = json.load(f)
                # Assuming JSON is like: ["Faces", "Sandbox", "VR"]
                if data and len(data) >= 3:
                    return ", ".join(data[:3])
        except Exception as e:
            logger.error(f"Failed to read LiDAR file: {e}")

# ============ MODELS ============
class ChatRequest(BaseModel):
    session_id: str
    user_text: str

class ChatResponse(BaseModel):
    reply_text: str
    emotion: str = "neutral"

class StartResponse(BaseModel):
    reply_text: str

class STTResponse(BaseModel):
    transcript: str
    confidence: float
    language: str
    processing_time_ms: int

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    format: Optional[str] = None 

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str

# ============ ENDPOINTS ============
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Exhibit Feedback Chatbot API...")
    load_exhibit_questions()

@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(status="healthy", service="App1", version="1.4.0", timestamp=datetime.now().isoformat())

@app.get("/start", response_model=StartResponse)
async def start_endpoint(session_id: str):
    # Reset session logic
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]
    
    # 1. Short, engaging hooks (Randomized)
    hooks = [
        "Your feedback helps shape the future of this exhibition.",
        "We use your thoughts to help researchers understand visitor experiences.",
        "I'm collecting data to help developers improve their exhibit.",
        "Your perspective helps us bridge the gap between data and people.",
        "I am the digital memory of this space, learning from every visitor.",
        "Your honest critique helps us make Data Spaces better for everyone."
    ]
    
    # 2. Standard Instruction (Constant)
    instruction = "Tap the button below and just say 'Yes' to begin."
    
    # 3. Combine them
    reply = f"{random.choice(hooks)} {instruction}"
    
    # Save to history so the bot knows it started the convo
    _append_message(session_id, "assistant", reply)
    
    return StartResponse(reply_text=reply)

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    s = _get_session(request.session_id)
    transition_note = None
    user_text = request.user_text

    # 1. Update History
    _append_message(request.session_id, "user", user_text)
    
    # 2. Logging
    if s["last_qid"] and s["last_qid"] not in ["select_exhibit", "ask_restart"]:
        log_feedback_event({
            "session_id": request.session_id,
            "exhibit": s.get("selected_exhibit", "unknown"),
            "question_id": s["last_qid"],
            "answer": user_text
        })
        
    # 3. Detect Switch
    detected = detect_exhibit_from_text(user_text)
    # === NEW: LLM Fallback Detection (The Fix) ===
    # If Python missed the keyword, let's ask the LLM to verify if an exhibit was mentioned.
    if not detected and not s["selected_exhibit"]:
        # Quick prompt to classify the user's intent
        classification_prompt = f"""
        You are a classifier. 
        User text: "{user_text}"
        
        Task: Does this text refer to one of these exhibits?
        Exhibits: {", ".join(EXHIBITS)}
        
        Output: Return ONLY the exact exhibit name. If unsure or no match, return "None".
        """
        # We reuse your existing call_llm function for consistency
        suspected = call_llm(classification_prompt, [])
        
        # Clean up response (remove punctuation/spaces)
        suspected = suspected.strip().strip(".\"")
        
        if suspected in EXHIBITS:
            detected = suspected
            logger.info(f"LLM Fallback detected exhibit: {detected}")
    # ===============================================

    # === NEW: Detect "Navigation Intent" (The Exception) ===
    # If no exhibit is found, check if the user is explicitly asking to switch/choose.
    if not detected:
        # Keywords that imply "I want to choose something else"
        nav_keywords = ["another", "other", "different", "something else", "review one", "switch"]
        if any(k in user_text.lower() for k in nav_keywords):
            s["force_open_choice"] = True
            logger.info("User explicitly asked to choose an exhibit.")
    # =======================================================

    # B. NEW: Intent Validation (The Fix for your issue)
    # If we have a current exhibit AND the detected one is different, check INTENT.
    current_ex = s.get("selected_exhibit")
    
    if current_ex and detected and detected != current_ex:
        # Ask LLM if this is a real switch
        validation_prompt = f"""
        Context: The user is currently discussing '{current_ex}'.
        User Input: "{request.user_text}"
        Detected Keyword: Refers to '{detected}'.
        Task: Determine if the user wants to SWITCH to '{detected}' or STAY on '{current_ex}' (referencing comparison).
        Output: Return exactly "SWITCH" or "STAY".
        """
        decision = call_llm(validation_prompt, [])  # Pass empty history for speed
        logger.info(f"Switch Validation: {decision}")
        
        if "stay" in decision.lower():
            # CASE: STAY
            # We ignore the new keyword, BUT we tell the LLM to acknowledge the choice.
            detected = current_ex 
            transition_note = (
                f"The user mentioned '{request.user_text}' but we are sticking to '{current_ex}'. "
                "Start your reply with: 'Okay, let's stick to this exhibit for now...'"
            )
        else:
            # CASE: SWITCH
            # We allow the switch, and tell the LLM to acknowledge it.
            transition_note = (
                f"The user explicitly switched from '{current_ex}' to '{detected}'. "
                f"Start your reply with: 'Okay, we can switch to the {detected}...'"
            )

    if detected:
        if detected != s["selected_exhibit"]:
            s["selected_exhibit"] = detected
            s["selection_attempts"] = 0  # <--- NEW: Reset counter if they pick one!
            log_feedback_event({"session_id": request.session_id, "type": "select", "exhibit": detected})
    elif "overall" in user_text.lower():
        s["selected_exhibit"] = "overall exhibition"

    s["turn_count"] += 1

    # 4. Closing Check
    forced_stop = any(x in user_text.lower() for x in ["bye", "stop", "exit", "quit"])
    if s["turn_count"] > MAX_USER_TURNS or forced_stop:
        prompt = build_unified_system_prompt("", None, None, is_closing=True)
        reply = call_llm(prompt, s["messages"])
        _append_message(request.session_id, "assistant", reply)
        return ChatResponse(reply_text=reply)

    # 5. Get Next Question Logic
    plan = get_next_question_logic(s)
    
    # === NEW: Check for Forced Exit Logic ===
    if plan.get("end_conversation"):
        prompt = build_unified_system_prompt("", None, None, is_closing=True)
        reply = call_llm(prompt, s["messages"])
        _append_message(request.session_id, "assistant", reply)
        return ChatResponse(reply_text=reply)
    # ========================================

    # 6. Generate Response
    system_prompt = build_unified_system_prompt(
        target_question=plan["text"],
        current_exhibit=s.get("selected_exhibit"),
        one_liner=plan["one_liner"],
        is_closing=False,
        transition_note=transition_note
    )
    
    reply = call_llm(system_prompt, s["messages"])
    
    # 7. Update State
    s["last_qid"] = plan["id"]
    if plan["id"] not in ["select_exhibit", "ask_restart"]:
        s["asked_qids"].add(plan["id"])
    _append_message(request.session_id, "assistant", reply)

    return ChatResponse(reply_text=reply)

# STT / TTS Endpoints
@app.post("/stt", response_model=STTResponse)
async def stt_endpoint(
    session_id: str = Form("default_session"),
    language: str = Form("en"),
    audio_file: UploadFile = File(..., description="WAV audio file")
):
    start = time.time()
    suffix = os.path.splitext(audio_file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        audio_bytes = await audio_file.read()
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            tr = client.audio.transcriptions.create(
                model=os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe"),
                file=f,
                language=language
            )
        ms = int((time.time() - start) * 1000)
        return STTResponse(transcript=(tr.text or "").strip(), confidence=1.0, language=language, processing_time_ms=ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try: os.remove(tmp_path)
        except: pass

@app.post("/tts")
async def tts_endpoint(request: TTSRequest):
    text = (request.text or "").strip()
    if not text: raise HTTPException(status_code=400, detail="Missing text")
    try:
        audio = client.audio.speech.create(
            model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            voice=request.voice or "coral",
            input=text,
            response_format=request.format or "mp3"
        )
        audio_bytes = audio if isinstance(audio, (bytes, bytearray)) else audio.read()
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)