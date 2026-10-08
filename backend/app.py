# ==============================================================================
# JEENI READER AI — COMPLETE PRODUCTION FASTAPI BACKEND SERVER
# ==============================================================================

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel
from typing import Tuple, Optional, List
import os
import re
import uuid
import time
import json
import io
import urllib.request
import urllib.parse
import pymupdf as fitz  # PyMuPDF
import sqlite3
from collections import Counter
from passlib.context import CryptContext
from deep_translator import GoogleTranslator, MyMemoryTranslator

# ------------------------------------------------------------------------------
# OPTIONAL LIBRARY IMPORTS (With Safe Fallbacks)
# ------------------------------------------------------------------------------

# Offline TTS (fallback only). Now optional so the server never crashes without it.
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

# Desktop RPA library for Windows Explorer automation
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# Local Tesseract OCR & Pillow image processing libraries
try:
    import pytesseract
    from PIL import Image
    LOCAL_OCR_AVAILABLE = True
except ImportError:
    LOCAL_OCR_AVAILABLE = False

# HTTP requests library for Cloud OCR fallback
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Google Text-to-Speech library (needed for Gujarati / Hindi / Marathi voice + MP3)
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    print("⚠️  gTTS is NOT installed. Gujarati/Hindi/Marathi voice will NOT work. Run: pip install gTTS")


# ------------------------------------------------------------------------------
# APPLICATION SETUP & CORS MIDDLEWARE
# ------------------------------------------------------------------------------
app = FastAPI(title="Jeeni Reader AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# PROJECT PATHS & DIRECTORY CREATION
# ------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
FRONT_DIR = os.path.join(PROJECT_DIR, "front")
if not os.path.exists(FRONT_DIR):
    FRONT_DIR = os.path.join(BASE_DIR, "front")

DB_FILE = os.path.join(BASE_DIR, "users.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRONT_DIR, exist_ok=True)

# Mount static frontend files if folder exists
if os.path.isdir(FRONT_DIR):
    app.mount("/static", StaticFiles(directory=FRONT_DIR), name="static")


# ------------------------------------------------------------------------------
# GEMINI API KEY & AUTHENTICATION CONFIGURATION
# ------------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
# Older model names get retired by Google. Change here (or via env var) if needed.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

LANG_NAMES = {"en": "English", "gu": "Gujarati", "hi": "Hindi", "mr": "Marathi"}


# ------------------------------------------------------------------------------
# PYDANTIC DATA MODELS
# ------------------------------------------------------------------------------
class UserRegister(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class SummarizeRequest(BaseModel):
    text: str
    max_sentences: Optional[int] = 3
    file_id: Optional[str] = "manual"
    file_name: Optional[str] = "Document Summary"
    lang: Optional[str] = "en"          # NEW: language the summary should be written in

class TranslationRequest(BaseModel):
    text: str
    target_lang: str

class TextToAudioRequest(BaseModel):
    text: str
    lang: Optional[str] = "en"

class ExportTranslationRequest(BaseModel):
    text: str
    filename: Optional[str] = "Jeeni_Translated_Document.txt"

class RPAPathRequest(BaseModel):
    filename: str

class SearchWordRequest(BaseModel):
    text: str
    keyword: str

class SaveBookmarkRequest(BaseModel):
    file_id: str
    current_page: int
    current_sentence: int


# ------------------------------------------------------------------------------
# 1. SQLITE DATABASE INITIALIZATION (With Auto Migration)
# ------------------------------------------------------------------------------
def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            file_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            total_pages INTEGER DEFAULT 1,
            characters INTEGER DEFAULT 0,
            extracted_text TEXT,
            uploaded_at TEXT NOT NULL DEFAULT ''
        )
        """)

        # Check & Auto-Add missing uploaded_at column if old DB exists
        cursor.execute("PRAGMA table_info(documents)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'uploaded_at' not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN uploaded_at TEXT DEFAULT ''")
            print("✅ Auto-migrated 'documents' table: added 'uploaded_at' column.")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            summary_id TEXT PRIMARY KEY,
            file_id TEXT,
            file_name TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            bookmark_id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            current_page INTEGER DEFAULT 1,
            current_sentence INTEGER DEFAULT 0,
            saved_at TEXT NOT NULL
        )
        """)

        conn.commit()
        conn.close()
        print(f"✅ SQLite Database initialized cleanly at: {DB_FILE}")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

init_db()


# ------------------------------------------------------------------------------
# HELPER UTILITIES, AUTH HASHING & TRANSLATION CHUNKING
# ------------------------------------------------------------------------------
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def clean_filename(filename: str) -> str:
    cleaned = re.sub(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_', '', filename, flags=re.IGNORECASE)
    return cleaned if cleaned else filename

def chunk_text(text: str, max_chunk_size: int = 3500) -> List[str]:
    """Splits long text into smaller chunks to satisfy Google Translate character limits."""
    sentences = re.split(r'(?<=[.!?\u0964\n])\s+', text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        # A single sentence longer than the limit: hard-split it
        while len(sentence) > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            chunks.append(sentence[:max_chunk_size])
            sentence = sentence[max_chunk_size:]
        if len(current_chunk) + len(sentence) + 1 > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
    if current_chunk:
        chunks.append(current_chunk)
    return chunks if chunks else [text[:max_chunk_size]]

def free_google_translate(text: str, target_lang: str) -> str:
    """Fallback translator using Google's free public translation endpoint via urllib."""
    try:
        chunks = chunk_text(text, max_chunk_size=1500)
        translated_parts = []
        for chunk in chunks:
            if not chunk.strip():
                continue
            encoded_query = urllib.parse.quote(chunk)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={encoded_query}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                part_text = "".join([part[0] for part in data[0] if part and len(part) > 0 and part[0]])
                translated_parts.append(part_text if part_text else chunk)
        return "\n\n".join(translated_parts)
    except Exception as e:
        print(f"Direct Google Translate Engine error: {e}")
        return ""

def make_gtts_mp3(text: str, lang: str) -> io.BytesIO:
    """Create an MP3 in memory using gTTS. Raises on failure."""
    if not GTTS_AVAILABLE:
        raise RuntimeError("gTTS library not installed (pip install gTTS)")
    tts = gTTS(text=text, lang=lang)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp


# ------------------------------------------------------------------------------
# 2. AUTHENTICATION ENDPOINTS (LOGIN & REGISTER)
# ------------------------------------------------------------------------------
@app.post("/auth/register")
@app.post("/api/auth/register")
def register_user(user: UserRegister):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE email = ?", (user.email,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = str(uuid.uuid4())
        hashed_pw = get_password_hash(user.password)

        cursor.execute(
            "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, user.name, user.email, hashed_pw)
        )
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": "User registered successfully",
            "user": {"id": user_id, "name": user.name, "email": user.email}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@app.post("/auth/login")
@app.post("/api/auth/login")
def login_user(user: UserLogin):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (user.email,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user_id, name, email, hashed_pw = row
        if not verify_password(user.password, hashed_pw):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        return {
            "status": "success",
            "message": "Login successful",
            "user": {"id": user_id, "name": name, "email": email},
            "token": str(uuid.uuid4())
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


# ------------------------------------------------------------------------------
# 3. DOCUMENT UPLOAD & AI OCR EXTRACTION ENDPOINTS
# ------------------------------------------------------------------------------
@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        file_ext = os.path.splitext(file.filename)[1].lower()
        unique_name = f"{uuid.uuid4()}_{file.filename}"
        saved_path = os.path.join(UPLOAD_DIR, unique_name)

        content = await file.read()
        with open(saved_path, "wb") as f:
            f.write(content)

        extracted_text = ""
        total_pages = 1

        if file_ext == ".pdf":
            doc = fitz.open(saved_path)
            total_pages = len(doc)
            pages_text = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages_text.append(text)
            doc.close()
            extracted_text = "\n\n".join(pages_text)

        elif file_ext in [".png", ".jpg", ".jpeg", ".webp"]:
            if LOCAL_OCR_AVAILABLE:
                img = Image.open(saved_path)
                extracted_text = pytesseract.image_to_string(img)
            else:
                extracted_text = f"[Image uploaded: {file.filename}. Tesseract OCR unavailable]"

        elif file_ext == ".txt":
            extracted_text = content.decode("utf-8", errors="ignore")
        else:
            extracted_text = content.decode("utf-8", errors="ignore")

        extracted_text = extracted_text.strip()
        file_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        clean_name = clean_filename(file.filename)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO documents
                   (file_id, file_name, file_path, file_type, total_pages, characters, extracted_text, uploaded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (file_id, clean_name, saved_path, file_ext, total_pages, len(extracted_text), extracted_text, timestamp)
            )
        except sqlite3.OperationalError as oe:
            if "uploaded_at" in str(oe):
                cursor.execute("ALTER TABLE documents ADD COLUMN uploaded_at TEXT DEFAULT ''")
                cursor.execute(
                    """INSERT INTO documents
                       (file_id, file_name, file_path, file_type, total_pages, characters, extracted_text, uploaded_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (file_id, clean_name, saved_path, file_ext, total_pages, len(extracted_text), extracted_text, timestamp)
                )
            else:
                raise oe
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": "File processed successfully!",
            "file_id": file_id,
            "id": file_id,
            "file_name": clean_name,
            "filename": clean_name,
            "total_pages": total_pages,
            "characters": len(extracted_text),
            "text": extracted_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ------------------------------------------------------------------------------
# 4. VAULT STORAGE & HISTORY ENDPOINTS
# ------------------------------------------------------------------------------
@app.get("/history")
@app.get("/vault/documents")
@app.get("/documents")
def list_documents():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, file_name, file_type, total_pages, characters, uploaded_at, extracted_text FROM documents ORDER BY uploaded_at DESC")
        rows = cursor.fetchall()
        conn.close()

        docs = []
        for r in rows:
            docs.append({
                "file_id": r[0],
                "id": r[0],
                "file_name": r[1],
                "filename": r[1],
                "file_type": r[2],
                "total_pages": r[3] if r[3] else 1,
                "characters": r[4] if r[4] else 0,
                "uploaded_at": r[5] or "Recently",
                "text_preview": (r[6] or "")[:150]
            })
        return docs
    except Exception as e:
        print(f"Error fetching history: {e}")
        return []


@app.get("/document/{file_id}")
@app.get("/vault/document/{file_id}")
def get_document(file_id: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, file_name, extracted_text, total_pages FROM documents WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "status": "success",
            "file_id": row[0],
            "id": row[0],
            "file_name": row[1],
            "filename": row[1],
            "extracted_text": row[2],
            "text": row[2],
            "total_pages": row[3]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/{file_id}")
@app.delete("/vault/document/{file_id}")
@app.delete("/delete/{file_id}")
def delete_document(file_id: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM documents WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()

        if row and os.path.exists(row[0]):
            try:
                os.remove(row[0])
            except Exception:
                pass

        cursor.execute("DELETE FROM documents WHERE file_id = ?", (file_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Document deleted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ------------------------------------------------------------------------------
# 5. GEMINI AI SUMMARIZATION, TTS, MP3 & TRANSLATION ENDPOINTS
# ------------------------------------------------------------------------------
@app.post("/summarize")
@app.post("/api/summaries")
def summarize_text(data: SummarizeRequest):
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided for summarization")

    lang_name = LANG_NAMES.get((data.lang or "en").lower(), "English")
    summary_result = ""

    if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            prompt = (
                f"Provide a clean, bulleted 3-point executive summary of the text below. "
                f"Write the summary in {lang_name}. Use '•' as bullet marker and no other markdown.\n\n"
                f"{text[:8000]}"
            )
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                summary_result = result['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            print(f"Gemini API warning: {e}, falling back to extractive summary.")

    if not summary_result:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?\u0964])\s+', text) if len(s.strip()) > 15]
        if sentences:
            summary_result = "• " + "\n• ".join(sentences[:data.max_sentences or 3])
        else:
            summary_result = "• " + text[:300] + "..."

    summary_id = str(uuid.uuid4())
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO summaries (summary_id, file_id, file_name, summary_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (summary_id, data.file_id, data.file_name, summary_result, created_at)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Summary DB save warning: {e}")

    return {
        "status": "success",
        "message": "Summary generated successfully",
        "summary_id": summary_id,
        "summary": summary_result,
        "created_at": created_at,
        "file_name": data.file_name
    }


@app.get("/api/summaries")
@app.get("/vault/summaries")
def get_summaries_history():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT summary_id, file_id, file_name, summary_text, created_at FROM summaries ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        summaries = []
        for r in rows:
            summaries.append({
                "id": r[0],
                "summary_id": r[0],
                "file_id": r[1],
                "file_name": r[2],
                "summary_text": r[3],
                "created_at": r[4]
            })
        return {"status": "success", "summaries": summaries}
    except Exception as e:
        return {"status": "error", "summaries": []}


@app.delete("/api/summaries/{summary_id}")
@app.delete("/vault/summary/{summary_id}")
def delete_summary(summary_id: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM summaries WHERE summary_id = ?", (summary_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Summary deleted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/tts")
def tts_stream(text: str, lang: Optional[str] = "en"):
    text_clean = text.strip()
    if not text_clean:
        raise HTTPException(status_code=400, detail="Empty text")

    target_l = lang if lang in ['en', 'hi', 'gu', 'mr'] else 'en'

    # Attempt 1: gTTS (Google voice for Gujarati, Hindi, Marathi, English)
    # NOTE: the frontend now sends short chunks (<=180 chars), so 600 is plenty.
    if GTTS_AVAILABLE:
        try:
            fp = make_gtts_mp3(text_clean[:600], target_l)
            return StreamingResponse(fp, media_type="audio/mpeg")
        except Exception as e:
            print(f"❌ gTTS error for lang '{target_l}': {e}")
    else:
        print("❌ /tts called but gTTS is not installed. Run: pip install gTTS")

    # Attempt 2: pyttsx3 offline fallback (usually has NO Gujarati/Hindi/Marathi voice)
    if PYTTSX3_AVAILABLE and target_l == "en":
        try:
            engine = pyttsx3.init()
            temp_wav = os.path.join(UPLOAD_DIR, f"speech_{uuid.uuid4().hex[:6]}.wav")
            engine.save_to_file(text_clean[:600], temp_wav)
            engine.runAndWait()
            if os.path.exists(temp_wav):
                with open(temp_wav, "rb") as f:
                    data = f.read()
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass
                return Response(content=data, media_type="audio/wav")
        except Exception as err:
            print(f"pyttsx3 error: {err}")

    raise HTTPException(
        status_code=500,
        detail="Voice audio generation failed. Install gTTS (pip install gTTS) and check internet connection."
    )


@app.post("/download_audio")
@app.post("/export_audio")
def export_audio(data: TextToAudioRequest):
    if not GTTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="gTTS library not installed on server.")

    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided for audio export.")

    lang = data.lang if data.lang in ['en', 'hi', 'gu', 'mr'] else "en"
    try:
        # gTTS splits long text internally, so a bigger limit is fine here
        fp = make_gtts_mp3(text[:5000], lang)

        filename = f"jeeni_audio_{uuid.uuid4().hex[:8]}.mp3"
        return StreamingResponse(
            fp,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio export failed: {str(e)}")


@app.post("/export_translation")
def export_translation(data: ExportTranslationRequest):
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text to export.")

    filename = data.filename or f"translated_{uuid.uuid4().hex[:6]}.txt"
    if not filename.endswith(".txt"):
        filename += ".txt"

    # Header values must be latin-1 safe, so encode the file name for non-English names
    safe_name = urllib.parse.quote(filename)
    buffer = io.BytesIO(text.encode("utf-8"))
    return StreamingResponse(
        buffer,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"}
    )


@app.post("/translate")
def translate_text(data: TranslationRequest):
    text = data.text.strip()
    target_lang = data.target_lang.strip().lower()

    if not text:
        return {"status": "success", "translated_text": "", "target_lang": target_lang}

    translated_result = ""

    # Attempt 1: Direct Google GTX Engine via urllib
    try:
        translated_result = free_google_translate(text, target_lang)
    except Exception as e:
        print(f"Attempt 1 failed: {e}")

    # Attempt 2: deep_translator GoogleTranslator
    if not translated_result:
        try:
            chunks = chunk_text(text, max_chunk_size=2500)
            parts = []
            for chunk in chunks:
                translator = GoogleTranslator(source='auto', target=target_lang)
                parts.append(translator.translate(chunk))
            translated_result = "\n\n".join(parts)
        except Exception as e:
            print(f"Attempt 2 failed: {e}")

    # Attempt 3: MyMemoryTranslator
    if not translated_result:
        try:
            chunks = chunk_text(text, max_chunk_size=450)   # MyMemory limit is ~500 chars
            parts = []
            for chunk in chunks:
                translator = MyMemoryTranslator(source='auto', target=target_lang)
                parts.append(translator.translate(chunk))
            translated_result = "\n\n".join(parts)
        except Exception as e:
            print(f"Attempt 3 failed: {e}")

    if translated_result:
        return {"status": "success", "translated_text": translated_result, "target_lang": target_lang}
    else:
        return {"status": "error", "translated_text": "", "message": "Translation failed. Check internet connection."}


@app.post("/rpa_select_file")
def rpa_select_file(data: RPAPathRequest):
    if not PYAUTOGUI_AVAILABLE:
        raise HTTPException(status_code=501, detail="pyautogui library not installed on server.")

    try:
        clean_name = data.filename.strip()
        clean_name = re.sub(r'\.(t|tx|txt)$', '', clean_name, flags=re.IGNORECASE)

        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        time.sleep(0.2)

        pyautogui.write(clean_name, interval=0.04)
        time.sleep(0.4)
        pyautogui.press('enter')
        return {"status": "success", "message": f"RPA typed '{clean_name}' and pressed Enter."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RPA execution failed: {str(e)}")


# ------------------------------------------------------------------------------
# 6. DIRECT HTML FILE ROUTER (Protected from API endpoints)
# ------------------------------------------------------------------------------
@app.get("/")
def serve_root():
    auth_path = os.path.join(FRONT_DIR, "auth.html")
    if os.path.exists(auth_path):
        return FileResponse(auth_path)
    return {"message": "Jeeni Reader AI Backend Server is Running!"}

@app.get("/{page_name:path}")
def serve_static_html(page_name: str):
    api_prefixes = ["api", "auth", "upload", "history", "documents", "document", "vault", "summarize", "tts", "download_audio", "export_audio", "translate", "rpa_select_file", "export_translation"]
    first_segment = page_name.split("/")[0]
    if first_segment in api_prefixes:
        raise HTTPException(status_code=404, detail="API endpoint not found")

    target_path = os.path.join(FRONT_DIR, page_name)
    if os.path.exists(target_path) and os.path.isfile(target_path):
        return FileResponse(target_path)
    raise HTTPException(status_code=404, detail="Not Found")


# ------------------------------------------------------------------------------
# SERVER ENTRYPOINT
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)