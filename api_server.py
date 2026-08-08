"""
api_server.py — REST API for CMT SA Voice Assistant.

Developers can pay for API access and call the assistant via HTTP.
Run separately from the Streamlit app:

    uvicorn api_server:app --host 0.0.0.0 --port 8000

Endpoints:
    POST /api/chat         — send text, get AI reply
    POST /api/translate     — translate between SA languages
    POST /api/tts           — text to speech, returns MP3
    POST /api/quiz          — generate a quiz
    GET  /api/languages     — list supported languages
    GET  /api/health        — health check

All endpoints require header: X-API-Key: <your-api-key>
"""

import os
import tempfile
import base64

try:
    from fastapi import FastAPI, HTTPException, Header, Depends
    from fastapi.responses import JSONResponse, FileResponse
    from pydantic import BaseModel
except ImportError:
    # FastAPI not installed — API server won't run but the main app still works
    pass

import db
import brain
import voices
import audio_helper

app = FastAPI(
    title="CMT SA Voice Assistant API",
    description="South African multilingual AI assistant API",
    version="1.0.0",
)


# ── API key auth ──────────────────────────────────────────────────────────────
API_KEYS = {}  # loaded from DB or env


def _load_api_keys():
    """Load API keys from environment. Format: CMT_API_KEYS=key1:email1,key2:email2"""
    raw = os.environ.get("CMT_API_KEYS", "")
    for pair in raw.split(","):
        if ":" in pair:
            key, email = pair.strip().split(":", 1)
            API_KEYS[key] = email


_load_api_keys()


async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    email = API_KEYS[x_api_key]
    if not db.can_send(email):
        raise HTTPException(status_code=429, detail="API quota exceeded. Upgrade your plan.")
    return email


# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    language: str = "isizulu"
    personality: str = "assistant"

class TranslateRequest(BaseModel):
    text: str
    from_language: str = "isizulu"
    to_language: str = "english"

class TTSRequest(BaseModel):
    text: str
    language: str = "isizulu"
    gender: str = "Female"

class QuizRequest(BaseModel):
    subject: str = "maths"
    language: str = "isizulu"
    grade: str = "12"
    num_questions: int = 5


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "CMT SA Voice Assistant API"}


@app.get("/api/languages")
async def list_languages():
    return {"languages": {k: v["display"] for k, v in voices.LANGUAGES.items()}}


@app.post("/api/chat")
async def chat(req: ChatRequest, email: str = Depends(verify_api_key)):
    lang_display = voices.LANGUAGES.get(req.language, voices.LANGUAGES["english"])["display"]
    reply = brain.think(req.message, lang_display, personality=req.personality)
    db.increment_prompt(email)
    return {"reply": reply, "language": req.language}


@app.post("/api/translate")
async def translate(req: TranslateRequest, email: str = Depends(verify_api_key)):
    from_display = voices.LANGUAGES.get(req.from_language, voices.LANGUAGES["english"])["display"]
    to_display = voices.LANGUAGES.get(req.to_language, voices.LANGUAGES["english"])["display"]
    result = brain.translate(req.text, from_display, to_display)
    db.increment_prompt(email)
    return {"translation": result, "from": req.from_language, "to": req.to_language}


@app.post("/api/tts")
async def text_to_speech(req: TTSRequest, email: str = Depends(verify_api_key)):
    voice_id = voices.get_voice_id(req.language, req.gender)
    path = audio_helper.synthesize_to_file(req.text, voice_id)
    with open(path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()
    os.unlink(path)
    db.increment_prompt(email)
    return {"audio_base64": audio_b64, "format": "mp3"}


@app.post("/api/quiz")
async def generate_quiz(req: QuizRequest, email: str = Depends(verify_api_key)):
    lang_display = voices.LANGUAGES.get(req.language, voices.LANGUAGES["english"])["display"]
    quiz = brain.generate_quiz(req.subject, lang_display, req.grade, req.num_questions)
    db.increment_prompt(email)
    return {"quiz": quiz, "subject": req.subject, "language": req.language}
