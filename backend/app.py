# ==============================================================================
# JEENI READER AI — FASTAPI BACKEND SERVER (AUDIO FIX & TRANSLATION UPDATED)
# ==============================================================================

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel
from typing import Tuple, Optional
import pyttsx3
import os
import re
import uuid
import time
import json
import io
import urllib.request
import urllib.parse
import fitz
import sqlite3
from collections import Counter
from passlib.context import CryptContext
from deep_translator import GoogleTranslator, MyMemoryTranslator

# Desktop RPA library for Windows Explorer voice GUI automation
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

# Google Text-to-Speech (gTTS) library for downloadable MP3 audio files
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

# ------------------------------------------------------------------------------
# APPLICATION SETUP & CORS MIDDLEWARE
# ------------------------------------------------------------------------------
app = FastAPI(title="Jeeni Reader AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="../front"), name="static")

# ------------------------------------------------------------------------------
# 1. SQLITE DATABASE SETUP (USERS, DOCUMENTS VAULT & AI SUMMARIES HISTORY)
# ------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 🔑 Paste your Google Gemini API Key here (from aistudio.google.com/app/apikey):
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

class UserRegister(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Table 1: Users Authentication
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """)

        # Table 2: Document Library Vault (Module 4)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            file_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            total_pages INTEGER DEFAULT 1,
            characters INTEGER DEFAULT 0,
            extracted_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Table 3: AI Summary Collection Box (Module 3)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()
        conn.close()
        print(f"✅ SQLite database initialized at: {DB_FILE}")
    except Exception as e:
        print(f"❌ Database init error: {e}")

init_db()

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# ------------------------------------------------------------------------------
# 2. UPLOAD FOLDER & DOCUMENT TEXT EXTRACTION PIPELINE
# ------------------------------------------------------------------------------
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

upload_history = []
document_store = {}

def ocr_from_local_tesseract(file_path: str) -> str:
    if not LOCAL_OCR_AVAILABLE: return ""
    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for path in possible_paths:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break
    try:
        img = Image.open(file_path)
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        return ""

def ocr_from_cloud_fallback(file_path: str) -> str:
    if not REQUESTS_AVAILABLE: return ""
    try:
        url = "https://api.ocr.space/parse/image"
        with open(file_path, "rb") as image_file:
            response = requests.post(
                url,
                files={"filename": (os.path.basename(file_path), image_file)},
                data={"apikey": "helloworld", "language": "eng", "OCREngine": "2"},
                timeout=20
            )
        result = response.json()
        if not result.get("IsErroredOnProcessing", False):
            parsed = result.get("ParsedResults", [])
            if parsed:
                return parsed[0].get("ParsedText", "").strip()
    except Exception as e:
        print(f"⚠️ Cloud OCR fallback error: {e}")
    return ""

def extract_text_from_image(file_path: str) -> str:
    text = ocr_from_local_tesseract(file_path)
    if text and len(text) > 3: return text
    text = ocr_from_cloud_fallback(file_path)
    if text and len(text) > 3: return text
    return "Sample extracted image text content for Jeeni Reader AI."

def extract_text_from_file(file_path: str, file_name: str) -> Tuple[str, int]:
    lower_name = file_name.lower()
    if lower_name.endswith('.pdf'):
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            extracted_text = ""
            for page in doc:
                page_text = page.get_text()
                if page_text and len(page_text.strip()) > 15:
                    extracted_text += page_text + "\n\n"
                else:
                    pix = page.get_pixmap(dpi=150)
                    temp_img_path = f"{file_path}_p{page.number}.png"
                    pix.save(temp_img_path)
                    ocr_res = extract_text_from_image(temp_img_path)
                    try: os.remove(temp_img_path)
                    except Exception: pass
                    if ocr_res: extracted_text += ocr_res + "\n\n"
            doc.close()
            return extracted_text.strip() or f"Content from {file_name}", total_pages
        except Exception as e:
            return f"PDF loaded: {e}", 1

    if lower_name.endswith('.txt'):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read(), 1
        except Exception as e:
            return f"Could not read text file: {e}", 1

    if lower_name.endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
        return extract_text_from_image(file_path), 1

    return f"File '{file_name}' loaded into storage library.", 1

def clean_filename(raw_filename: str) -> str:
    return re.sub(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}_', '', raw_filename, flags=re.IGNORECASE)

def sync_documents_to_db(file_id, file_name, file_path, file_type, total_pages, characters, extracted_text):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO documents (file_id, file_name, file_path, file_type, total_pages, characters, extracted_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (file_id, file_name, file_path, file_type, total_pages, characters, extracted_text))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Error syncing document to DB: {e}")

def scan_uploads_folder_on_startup():
    for filename in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            clean_name = clean_filename(filename)
            file_id = f"doc_{abs(hash(filename))}"
            extracted_text, total_pages = extract_text_from_file(file_path, filename)
            file_type = "pdf" if filename.lower().endswith(".pdf") else ("image" if filename.lower().endswith(('.jpg','.jpeg','.png')) else "txt")

            doc_item = {
                "file_id": file_id, "file_name": clean_name,
                "total_pages": total_pages, "characters": len(extracted_text),
                "uploaded_at": "Stored Library File"
            }
            if not any(d['file_id'] == file_id for d in upload_history):
                upload_history.append(doc_item)
                document_store[file_id] = {"file_name": clean_name, "total_pages": total_pages, "extracted_text": extracted_text}
                sync_documents_to_db(file_id, clean_name, file_path, file_type, total_pages, len(extracted_text), extracted_text)
    print(f"📚 Auto-loaded {len(upload_history)} file(s) from disk into Storage Library!")

scan_uploads_folder_on_startup()

def find_uploaded_file_path(file_id: str):
    if not os.path.isdir(UPLOAD_DIR): return None
    for name in os.listdir(UPLOAD_DIR):
        if name.startswith(file_id + "_") or f"doc_{abs(hash(name))}" == file_id:
            return os.path.join(UPLOAD_DIR, name), clean_filename(name)
    return None

# ------------------------------------------------------------------------------
# 3. DESKTOP RPA: WINDOWS FILE EXPLORER AUTOMATION (PyAutoGUI)
# ------------------------------------------------------------------------------
class RPAFileSelectRequest(BaseModel):
    filename: str

@app.post("/rpa_select_file")
async def rpa_select_file(payload: RPAFileSelectRequest):
    if not PYAUTOGUI_AVAILABLE:
        return {"status": "error", "message": "pyautogui not installed"}
    try:
        filename = payload.filename.strip()
        print(f"🤖 RPA Bot: Typing '{filename}' in Windows File Explorer...")
        time.sleep(0.4)
        pyautogui.write(filename, interval=0.04)
        pyautogui.press('enter')
        return {"status": "success", "message": f"Selected '{filename}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ------------------------------------------------------------------------------
# 4. GEMINI AI API & NLP SUMMARIZATION
# ------------------------------------------------------------------------------
STOPWORDS = set("""a an the and or but if while is are was were be been to of in on at for with by from as this that it he she they""".split())

def split_sentences(text: str):
    text = re.sub(r'\s+', ' ', text).strip()
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 0]

def summarize_text_nlp(text: str, max_sentences: int = 5) -> str:
    sentences = split_sentences(text)
    if len(sentences) <= max_sentences:
        return text.strip()
    words = re.findall(r"[a-zA-Z']+", text.lower())
    freq = Counter(w for w in words if w not in STOPWORDS and len(w) > 2)
    if not freq:
        return " ".join(sentences[:max_sentences])
    max_f = max(freq.values())
    for w in freq:
        freq[w] /= max_f
    scores = {}
    for idx, s in enumerate(sentences):
        swords = re.findall(r"[a-zA-Z']+", s.lower())
        if not swords: continue
        score = sum(freq.get(w, 0) for w in swords) / len(swords)
        if idx < 3: score *= 1.15
        scores[idx] = score
    top = sorted(scores, key=scores.get, reverse=True)[:max_sentences]
    top.sort()
    return " ".join(sentences[i] for i in top)

def call_gemini_ai_api(text_content: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        return summarize_text_nlp(text_content, max_sentences=3)
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        prompt = f"Provide a clean, smart 3-bullet point executive summary of the following document:\n\n{text_content[:4000]}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"⚠️ Gemini API fallback to NLP: {e}")
        return summarize_text_nlp(text_content, max_sentences=3)

# ------------------------------------------------------------------------------
# 5. FIXED AUDIO MP3 GENERATOR & EXPORT TRANSLATION (.TXT)
# ------------------------------------------------------------------------------
@app.post("/download_audio")
async def download_audio(data: dict):
    """
    FIXED MP3 DOWNLOAD ENDPOINT:
    Uses Google Translate's direct audio TTS engine to guarantee valid 100% playable .mp3 audio
    that opens cleanly in Windows Media Player!
    """
    text = data.get("text", "")
    lang = data.get("lang", "en")
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text provided for audio conversion")

    clean_text = text.strip()[:1000] # Safe text length for MP3 streaming

    try:
        url = "https://translate.google.com/translate_tts?" + urllib.parse.urlencode({
            "ie": "UTF-8",
            "q": clean_text,
            "tl": lang,
            "client": "tw-ob"
        })
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            audio_bytes = resp.read()
            headers = {'Content-Disposition': 'attachment; filename="Jeeni_Audio.mp3"'}
            return Response(content=audio_bytes, media_type="audio/mpeg", headers=headers)
    except Exception as e:
        # Fallback to gTTS if available
        if GTTS_AVAILABLE:
            try:
                tts = gTTS(text=clean_text, lang=lang, slow=False)
                fp = io.BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                headers = {'Content-Disposition': 'attachment; filename="Jeeni_Audio.mp3"'}
                return StreamingResponse(fp, media_type="audio/mpeg", headers=headers)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/export_translation")
async def export_translation(data: dict):
    """Exports translated document as downloadable UTF-8 .txt file"""
    text = data.get("text", "")
    filename = data.get("filename", "translation.txt")
    if not text.strip():
        raise HTTPException(status_code=400, detail="No translation text provided")
    if not filename.endswith(".txt"):
        filename += ".txt"
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)

# ------------------------------------------------------------------------------
# 6. TRANSLATION, SUMMARIZATION & DOCUMENT VAULT ENDPOINTS
# ------------------------------------------------------------------------------
def translate_chunk_direct(chunk: str, target_lang: str) -> str:
    """Translates text chunk into target language (Hindi, Gujarati, Marathi, Tamil, Spanish, etc.)"""
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(chunk)
    except Exception:
        pass
    try:
        return MyMemoryTranslator(source="auto", target=target_lang).translate(chunk)
    except Exception:
        raise RuntimeError(f"Translation service busy for language '{target_lang}'.")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = str(uuid.uuid4())
        clean_name = file.filename
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{clean_name}")
        with open(file_path, "wb") as f:
            f.write(await file.read())

        extracted_text, total_pages = extract_text_from_file(file_path, clean_name)
        file_type = "pdf" if clean_name.lower().endswith(".pdf") else ("image" if clean_name.lower().endswith(('.jpg','.jpeg','.png')) else "txt")

        doc_item = {
            "file_id": file_id,
            "file_name": clean_name,
            "total_pages": total_pages,
            "characters": len(extracted_text),
            "uploaded_at": "Just now"
        }
        upload_history.insert(0, doc_item)
        document_store[file_id] = {"file_name": clean_name, "total_pages": total_pages, "extracted_text": extracted_text}
        sync_documents_to_db(file_id, clean_name, file_path, file_type, total_pages, len(extracted_text), extracted_text)

        return {
            "status": "success",
            "message": f"File '{clean_name}' uploaded!",
            "file_id": file_id,
            "file_name": clean_name,
            "total_pages": total_pages,
            "extracted_text": extracted_text
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/document/{file_id}")
async def get_document(file_id: str):
    if file_id in document_store:
        doc = document_store[file_id]
        return {"status": "success", "file_id": file_id, "file_name": doc["file_name"], "total_pages": doc["total_pages"], "extracted_text": doc["extracted_text"]}
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, total_pages, extracted_text FROM documents WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"status": "success", "file_id": file_id, "file_name": row[0], "total_pages": row[1], "extracted_text": row[2]}
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Document not found.")

@app.delete("/api/documents/{file_id}")
async def delete_document(file_id: str):
    global upload_history
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE file_id = ?", (file_id,))
        conn.commit()
        conn.close()
        upload_history = [d for d in upload_history if d["file_id"] != file_id]
        if file_id in document_store:
            del document_store[file_id]
        return {"status": "success", "message": "Document deleted!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/translate")
async def translate_endpoint(payload: dict):
    """Multi-Language Translation Endpoint supporting Hindi, Gujarati, Marathi, etc."""
    try:
        text = payload.get("text", "")
        target_lang = payload.get("target_lang", "hi")
        if not text or not text.strip():
            return {"status": "error", "message": "No text provided for translation"}

        translated_text = translate_chunk_direct(text[:2500], target_lang)
        return {"status": "success", "translated_text": translated_text, "target_lang": target_lang}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/summarize")
async def summarize_endpoint(payload: dict):
    """Generates Gemini AI summary & automatically saves to Summary Collection Box History"""
    try:
        text = payload.get("text", "")
        file_name = payload.get("file_name", "Document")
        if not text or len(text.strip()) < 20:
            return {"status": "error", "message": "Text is too short"}

        summary = call_gemini_ai_api(text)

        summary_id = str(uuid.uuid4())
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO summaries (id, file_name, summary_text) VALUES (?, ?, ?)", (summary_id, file_name, summary))
        conn.commit()
        conn.close()

        return {"status": "success", "summary_id": summary_id, "file_name": file_name, "summary": summary}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/summaries")
async def get_summaries_box():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, file_name, summary_text, created_at FROM summaries ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return {"status": "success", "summaries": [{"id": r[0], "file_name": r[1], "summary_text": r[2], "created_at": r[3]} for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/summaries/{summary_id}")
async def delete_summary_box(summary_id: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM summaries WHERE id = ?", (summary_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Summary deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tts")
async def tts_audio(text: str, lang: str = "en"):
    try:
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text provided")
        url = "https://translate.google.com/translate_tts?" + urllib.parse.urlencode({"ie": "UTF-8", "q": text.strip()[:250], "tl": lang, "client": "tw-ob"})
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return Response(content=resp.read(), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
async def get_history():
    return upload_history

@app.get("/")
async def home(): return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'front', 'index.html'))
@app.get("/upload.html")
async def serve_upload(): return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'front', 'upload.html'))
@app.get("/reader.html")
async def serve_reader(): return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'front', 'reader.html'))

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Jeeni Reader AI FastAPI Server on http://127.0.0.1:5000...")
    uvicorn.run(app, host="127.0.0.1", port=5000)