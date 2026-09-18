from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 👈 IMPORT ADD KARO
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Tuple, Optional
import pyttsx3
import os
import re
import uuid
import fitz
import sqlite3
from collections import Counter
from passlib.context import CryptContext
from deep_translator import GoogleTranslator

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ FIX: Static Folder Serve karo
# Ab browser /static/rpa.jpg request karega toh front folder se image mil jayegi
app.mount("/static", StaticFiles(directory="../front"), name="static")

# ---------------------------------------------------------
# SQLITE & AUTH SETUP
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.db")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """)
        conn.commit()
        conn.close()
        print(f"✅ SQLite database initialized at: {DB_FILE}")
    except Exception as e:
        print(f"❌ Database init error: {e}")

init_db()

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# ---------------------------------------------------------
# UPLOAD & HISTORY SETUP
# ---------------------------------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

upload_history = []
document_store = {}

def extract_text_from_file(file_path: str, file_name: str) -> Tuple[str, int]:
    lower_name = file_name.lower()
    if lower_name.endswith('.pdf'):
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            extracted_text = ""
            for page in doc:
                extracted_text += page.get_text() + "\n\n"
            doc.close()
            return extracted_text, total_pages
        except Exception:
            return "Could not extract text from PDF.", 0
    if lower_name.endswith('.txt'):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return content, 1
        except Exception as e:
            return f"Could not read text file: {e}", 0
    return (f"File '{file_name}' uploaded, but text extraction for this "
            f"file type isn't implemented on the backend yet (only .pdf "
            f"and .txt are supported right now)."), 1

def find_uploaded_file_path(file_id: str):
    if not os.path.isdir(UPLOAD_DIR):
        return None
    for name in os.listdir(UPLOAD_DIR):
        if name.startswith(file_id + "_"):
            return os.path.join(UPLOAD_DIR, name), name[len(file_id) + 1:]
    return None

STOPWORDS = set("""
a an the and or but if while is are was were be been being to of in on at
for with by from as this that these those it its it's he she they them his
her their our your my we you i not no do does did doing have has had having
so than then there here what which who whom when where why how all any both
each few more most other some such only own same can will just don should now
""".split())

def split_sentences(text: str):
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 0]

def summarize_text(text: str, max_sentences: int = 5) -> str:
    sentences = split_sentences(text)
    if len(sentences) <= max_sentences:
        return text.strip()

    words = re.findall(r"[a-zA-Z']+", text.lower())
    freq = Counter(w for w in words if w not in STOPWORDS and len(w) > 2)

    if not freq:
        return " ".join(sentences[:max_sentences])

    max_freq = max(freq.values())
    for w in freq:
        freq[w] = freq[w] / max_freq

    sentence_scores = {}
    for idx, sentence in enumerate(sentences):
        sentence_words = re.findall(r"[a-zA-Z']+", sentence.lower())
        if not sentence_words:
            continue
        score = sum(freq.get(w, 0) for w in sentence_words) / len(sentence_words)
        if idx < 3:
            score *= 1.15
        sentence_scores[idx] = score

    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:max_sentences]
    top_indices.sort()
    summary = " ".join(sentences[i] for i in top_indices)
    return summary

# ---------------------------------------------------------
# 1. AUTH ROUTES
# ---------------------------------------------------------
@app.post("/auth/register", status_code=201)
async def register_user(user: UserRegister):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM users WHERE email = ?", (user.email,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Email already registered")
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(user.password)
        cursor.execute(
            "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, user.name, user.email, hashed_password)
        )
        conn.commit()
        conn.close()
        return {"status": "success", "message": "User registered successfully!", "user_id": user_id}
    except Exception as e:
        print(f"🔥 Register Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/login")
async def login_user(user: UserLogin):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, password_hash FROM users WHERE email = ?", (user.email,))
        row = cursor.fetchone()
        conn.close()
        if not row or not verify_password(user.password, row[2]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token = f"token_{uuid.uuid4()}"
        return {
            "status": "success",
            "message": "Login successful",
            "token": token,
            "user": {"id": row[0], "name": row[1], "email": user.email}
        }
    except Exception as e:
        print(f"🔥 Login Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/profile")
async def get_profile(token: str = None):
    if not token:
        raise HTTPException(status_code=401, detail="Token missing")
    return {"status": "success", "data": {"id": "123", "name": "Test User", "email": "test@example.com"}}

# ---------------------------------------------------------
# 2. TTS & RPA Route
# ---------------------------------------------------------
@app.post("/run_rpa")
async def run_automation(text: str = None):
    try:
        if not text:
            return {"error": "No text provided"}
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        return {"stdout": "TTS completed successfully!", "stderr": ""}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------
# 3. Upload & Extract Text
# ---------------------------------------------------------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        extracted_text, total_pages = extract_text_from_file(file_path, file.filename)
        upload_history.insert(0, {
            "file_id": file_id,
            "file_name": file.filename,
            "total_pages": total_pages,
            "characters": len(extracted_text),
            "uploaded_at": "Just now"
        })
        document_store[file_id] = {
            "file_name": file.filename,
            "total_pages": total_pages,
            "extracted_text": extracted_text
        }
        return {
            "status": "success",
            "message": f"File '{file.filename}' uploaded successfully!",
            "file_id": file_id,
            "file_path": file_path,
            "file_name": file.filename,
            "total_pages": total_pages,
            "extracted_text": extracted_text
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------
# 4. Fetch Document by ID
# ---------------------------------------------------------
@app.get("/document/{file_id}")
async def get_document(file_id: str):
    doc = document_store.get(file_id)
    if doc:
        return {
            "status": "success",
            "file_id": file_id,
            "file_name": doc["file_name"],
            "total_pages": doc["total_pages"],
            "extracted_text": doc["extracted_text"]
        }
    found = find_uploaded_file_path(file_id)
    if not found:
        raise HTTPException(status_code=404, detail="Document not found.")
    file_path, original_name = found
    extracted_text, total_pages = extract_text_from_file(file_path, original_name)
    document_store[file_id] = {
        "file_name": original_name,
        "total_pages": total_pages,
        "extracted_text": extracted_text
    }
    return {
        "status": "success",
        "file_id": file_id,
        "file_name": original_name,
        "total_pages": total_pages,
        "extracted_text": extracted_text
    }

# ---------------------------------------------------------
# 5. Translate
# ---------------------------------------------------------
class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "hi"

@app.post("/translate")
async def translate_text(payload: TranslateRequest):
    try:
        text = payload.text
        target_lang = payload.target_lang
        if not text or len(text.strip()) < 1:
            return {"status": "error", "message": "No text provided"}
        MAX_CHUNK = 4500
        chunks = [text[i:i + MAX_CHUNK] for i in range(0, len(text), MAX_CHUNK)]
        translator = GoogleTranslator(source="auto", target=target_lang)
        translated_chunks = [translator.translate(chunk) for chunk in chunks]
        translated_text = "".join(translated_chunks)
        return {
            "status": "success",
            "translated_text": translated_text,
            "target_lang": target_lang
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------
# 6. Summarize
# ---------------------------------------------------------
class SummarizeRequest(BaseModel):
    text: str
    max_sentences: Optional[int] = 5

@app.post("/summarize")
async def summarize_endpoint(payload: SummarizeRequest):
    try:
        text = payload.text
        if not text or len(text.strip()) < 20:
            return {"status": "error", "message": "Text is too short to summarize."}
        max_sentences = payload.max_sentences or 5
        summary = summarize_text(text, max_sentences=max_sentences)
        return {
            "status": "success",
            "summary": summary,
            "original_length": len(text),
            "summary_length": len(summary)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------
# 7. History
# ---------------------------------------------------------
@app.get("/history")
async def get_history():
    return upload_history

# ---------------------------------------------------------
# 8. Serve HTML Pages
# ---------------------------------------------------------
@app.get("/")
async def home():
    return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'front', 'index.html'))

@app.get("/auth.html")
async def serve_auth():
    return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'front', 'auth.html'))

@app.get("/upload.html")
async def serve_upload():
    return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'front', 'upload.html'))

@app.get("/reader.html")
async def serve_reader():
    return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'front', 'reader.html'))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)