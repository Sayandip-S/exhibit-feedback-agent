# 🧠 Exhibit Feedback Backend (FastAPI)

This is the Python backend for the **Data Spaces Exhibition** feedback system. It serves as the "Embodied Subconscious" of the exhibition, designed to conduct controlled, meaningful interviews with visitors via a Unity frontend.

Unlike standard chatbots, this system uses a **Semi-Structured State Machine** to drive conversations toward actionable data (Emotion → Reason → Improvement) while maintaining a natural, conversational persona.

## 📂 Project Structure

```text
backend/
├── data/
│   ├── exhibit_questions.json    # The "Brain": Definitions & Question packs for all exhibits
│   └── feedback_log.jsonl        # (Ignored) Structured logs of visitor answers
├── config.py                     # Smart Keyword Mapping configuration
├── main.py                       # The Application Entry Point (FastAPI)
├── .env                          # API Keys (Do not commit)
└── requirements.txt              # Python Dependencies

<<<<<<< HEAD
## ⚙️ Core Logic Explained

### 1. The "Interviewer" State Machine

=======
#⚙️ Core Logic Explained
1. The "Interviewer" State Machine
>>>>>>> e93fac9e6daba498c372be1cff591048b9ef7a0c
The chatbot is not a free-form AI. It enforces a strict flow to ensure data quality:

#### Phase 1: Identification
The bot listens for keywords (e.g., "sand", "bacteria", "VR") using the smart mapping in `config.py` to identify the specific exhibit.

#### Phase 2: The Interview
Once an exhibit is locked, it pulls a specific "Question Pack" from `exhibit_questions.json` with three question types:
- **Emotion**: How does this exhibit make you feel?
- **Reason**: What aspects contribute to this feeling?
- **Improvement**: How could this experience be enhanced?

#### Phase 3: The Unified Prompt
We use a dynamic System Prompt that:
- Injects the current interview goal (e.g., "You MUST ask about safety")
- Provides a "Knowledge Base" of museum exhibits so the AI can answer factual questions
- Maintains conversational flow while gently guiding back to the interview structure

#### Phase 4: Closing
After a set number of turns (default: 5), the bot:
- Summarizes the user's feedback
- Thanks the visitor for their input
- Politely ends the session

---

### 2. Smart Context Mapping

The system solves the "Context Blindness" problem of LLMs using two layers:

#### Keyword Mapping (`config.py`)
Maps fuzzy user terms to official exhibit IDs:
- "t-shirt" → "Seamless pattern"
- "flood" → "Dresden mapping"
- "sand" → "Flood protection system"
- "bacteria" → "Microbial fuel cell"

#### Global Knowledge Injection
The system pre-loads one-liner descriptions of every exhibit into the context window:

**Example Knowledge Base:**

#🛠️ Setup & Installation
Prerequisites: Python 3.9+

Navigate to the backend directory:

Bash
cd backend
Create a virtual environment:

Bash
python -m venv venv

# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
Install dependencies:

Bash
pip install -r requirements.txt
Configuration: Create a file named .env in the backend/ folder and add your credentials:

Ini, TOML
OPENAI_API_KEY=sk-your-openai-key-here
OPENAI_MODEL=gpt-4o-mini

# Optional Configuration
MAX_USER_TURNS=5
FEEDBACK_LOG_PATH=data/feedback_log.jsonl

#🚀 Running the Server
Start the live server using Uvicorn. The Unity client can connect to this address.

Bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
Local Swagger UI: Visit http://localhost:8000/docs to test endpoints manually.

Health Check: http://localhost:8000/ should return {"status": "healthy"}.

🔌 API EndpointsMethodEndpointDescriptionGET/startResets the session and generates a random "Hook" question to start the chat.POST/chatThe main logic loop. Accepts user text, updates state, and returns the AI response + current emotion.POST/sttSpeech-to-Text: Accepts a .wav file and returns the transcript using OpenAI Whisper.POST/ttsText-to-Speech: Accepts text and returns streaming audio bytes (MP3) using OpenAI TTS.

#📊 Data Logging
All visitor feedback is automatically structured and logged to data/feedback_log.jsonl.

Example Log Entry:

JSON
{
  "session_id": "user_123",
  "type": "answer",
  "exhibit": "VR experience",
  "question_id": "vr_comfort",
  "answer": "It made me feel a bit dizzy but the visuals were cool.",
  "ts": "2023-10-27T10:00:00"
}
<<<<<<< HEAD

=======
>>>>>>> e93fac9e6daba498c372be1cff591048b9ef7a0c
