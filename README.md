<img width="320" height="148" alt="download" src="https://github.com/user-attachments/assets/d6002195-553b-41ea-b198-f7b7c281cbb5" />
Why I Built This Project (The Story Behind Jeeni Reader AI)

The inspiration for **Jeeni Reader AI** came from a personal everyday challenge: **multitasking while commuting**.
When I am traveling on a **bike or in a car**, I cannot physically look at my phone or laptop screen to read important documents, PDFs, or study notes. I needed a way to:
1. **Listen to my documents** completely hands-free while riding or driving.
2. **Control everything using voice commands** (like `"read page"`, `"pause"`, `"summarize"`, `"next"`) without touching the screen.
3. **Get quick AI summaries and translations** (in Hindi/Gujarati) on the go.
That's why I created **Jeeni Reader AI** — an all-in-one accessibility tool that converts any document into an interactive, voice-controlled audio experience!

<img width="320" height="165" alt="download" src="https://github.com/user-attachments/assets/81ab20ed-ed65-4ee5-951e-fc147b627e00" />


##  System Pipeline

```mermaid
flowchart TD
    User["👤 User (Commuting on Bike/Car)"] -->|Voice Command / Upload| App["📱 Jeeni Reader AI"]
    App -->|Scanned Images| OCR["👁️ AI OCR Engine"]
    App -->|Documents| Parser["📄 Text Parser"]
    
    OCR --> RawText["📝 Extracted Text"]
    Parser --> RawText
    
    RawText -->|Summarize| Gemini["🤖 Google Gemini AI"]
    RawText -->|Translate| Translator["🌐 Language Translator (Gujarati/Hindi)"]
    RawText -->|Convert to Voice| TTS["🔊 Text-to-Speech Engine"]
    
    Gemini --> Summary["📌 AI Summary"]
    Translator --> TransText["🌐 Translated Text"]
    TTS --> MP3["🎧 MP3 Audio / Read Aloud"]
    
    Summary --> Vault["📂 Document Vault & WhatsApp Share"]
    TransText --> Vault
    MP3 --> Vault




