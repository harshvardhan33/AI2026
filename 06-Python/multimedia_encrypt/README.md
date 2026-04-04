# Encrypted Multimedia Vault

A privacy-first file storage system built with FastAPI. Files are encrypted at rest using **AES-256-GCM** and decrypted only on demand via a hold-to-reveal mechanism — the moment you release, all content is wiped from the browser.

An **agentic AI analysis pipeline** (LangGraph) runs automatically after every upload, providing contextual understanding: image captions, object detection, OCR, audio transcription, sentiment analysis, and named entity recognition — all fully local, no API keys required.

---

## Features

- AES-256-GCM encryption with a unique key and random nonce per file
- Files split into 64 KB chunks — each chunk encrypted independently
- Keys stored physically separate from encrypted chunks
- Short-lived session tokens (30s TTL) bound to specific files
- Hold-to-reveal UI — parallel chunk streaming, wipe on release
- Delete files permanently from the vault
- **Agentic AI pipeline** — LangGraph supervisor routes to specialised crews:
  - **Text**: Named Entity Recognition + summarization
  - **Audio**: Whisper transcription + sentiment analysis
  - **Image**: BLIP contextual captioning + YOLOv8 object detection + OCR
  - **Video**: keyframe scene descriptions + object detection + audio transcription
- Structured logging with per-step latency to `logs/app.log`

---

## Supported File Types

| Type  | Formats                          |
|-------|----------------------------------|
| Text  | `.txt`                           |
| Image | `.jpg`, `.png`, `.gif`, `.webp`  |
| Audio | `.mp3`, `.ogg`, `.wav`, `.webm`  |
| Video | `.mp4`, `.webm`, `.ogv`          |

---

## System Dependencies

These must be installed on the host before running locally:

| Dependency    | Purpose                              | Install (Windows)                        |
|---------------|--------------------------------------|------------------------------------------|
| **FFmpeg**    | Whisper audio decoding, video audio  | `winget install ffmpeg`                  |
| **Tesseract** | OCR on images                        | [UB Mannheim installer][tesseract-dl]    |

[tesseract-dl]: https://github.com/UB-Mannheim/tesseract/wiki

Both degrade gracefully if missing — the rest of the analysis still runs and the error is logged.

> **Windows note:** Tesseract's path is hardcoded in `app/agents/image_crew.py` to
> `C:\Program Files\Tesseract-OCR\tesseract.exe` (the default UB Mannheim install location).
> If you installed it elsewhere, update that line accordingly.

---

## Project Structure

```
multimedia_encrypt/
├── app/
│   ├── config.py           # Settings: chunk size, TTL, MIME allowlist, paths
│   ├── crypto.py           # AES-256-GCM encrypt / decrypt
│   ├── logger.py           # Centralised structured logging (logs/app.log)
│   ├── storage.py          # Chunking, manifest, key storage, analysis I/O
│   ├── sessions.py         # In-memory session tokens with TTL + chunk tracking
│   ├── main.py             # FastAPI app entry point
│   ├── agents/
│   │   ├── orchestrator.py # LangGraph StateGraph supervisor
│   │   ├── text_crew.py    # spaCy NER + DistilBART summarization
│   │   ├── audio_crew.py   # Whisper transcription + CardiffNLP sentiment
│   │   ├── image_crew.py   # BLIP captioning + YOLOv8n + pytesseract OCR
│   │   └── video_crew.py   # OpenCV keyframes + image crew + audio crew
│   └── routers/
│       ├── upload.py       # POST /api/upload
│       ├── files.py        # GET /api/files, DELETE /api/files/{file_id}
│       ├── reveal.py       # POST/GET/DELETE /api/reveal/*
│       └── analysis.py     # GET /api/files/{file_id}/analysis
├── static/
│   ├── index.html
│   ├── app.js              # Hold-to-reveal, parallel chunk streaming, analysis modal
│   └── style.css
├── data/                   # Runtime storage (gitignored)
│   ├── files/              # Encrypted chunks + manifests + analysis.json
│   └── keys/               # AES keys (never colocated with chunks)
├── logs/                   # Application logs (gitignored)
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Local Setup & Run

```bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 2. Install Python dependencies
#    CPU-only PyTorch (avoids pulling the large CUDA build)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 3. Download spaCy language model
python -m spacy download en_core_web_sm

# 4. Start the server
uvicorn app.main:app --reload --port 9000
```

Open `http://127.0.0.1:9000` in your browser.
Interactive API docs: `http://127.0.0.1:9000/docs`

> **First upload note:** AI models are downloaded on first use.
> Whisper (~150 MB), BLIP (~900 MB), and DistilBART (~900 MB) will be fetched
> from Hugging Face automatically. Subsequent runs use the local cache.

---

## Docker

```bash
# Build
docker build -t multimedia-vault .

# Run (mounts data and logs as volumes so files persist across restarts)
docker run -p 9000:9000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  multimedia-vault
```

The Dockerfile installs FFmpeg and Tesseract automatically. AI models are downloaded on first use inside the container. To pre-bake them into the image (zero cold-start latency), uncomment the `RUN python -c ...` blocks in the Dockerfile — note this adds ~2 GB to the image size.

---

## How It Works

### Upload → Encrypt → Analyse
1. File validated (MIME type + size)
2. Split into 64 KB chunks, each AES-256-GCM encrypted with a fresh nonce
3. Encrypted chunks saved to `data/files/<file_id>/chunks/`
4. AES key saved separately to `data/keys/<file_id>.key`
5. Manifest (metadata JSON) saved alongside chunks
6. **AI analysis triggered as a background task** — result saved to `analysis.json`

### Reveal (hold-to-reveal)
1. Client requests a 30-second session token bound to the file
2. All chunk requests fire in **parallel** (`Promise.all`)
3. Server decrypts each chunk on the fly and returns raw bytes
4. Browser reassembles chunks into a Blob and renders content
5. On release: DOM wiped instantly, token revoked server-side

### AI Analysis Pipeline (LangGraph)
```
Upload → [Supervisor] → routes by MIME type
              │
    ┌─────────┼─────────┬─────────┐
    ▼         ▼         ▼         ▼
 text_crew  audio_crew image_crew video_crew
    │         │         │         │
   NER      Whisper   BLIP     keyframes
  BART     sentiment  YOLO   + image_crew
                       OCR   + audio_crew
```

---

## API Reference

| Method   | Endpoint                                    | Description                        |
|----------|---------------------------------------------|------------------------------------|
| `POST`   | `/api/upload`                               | Upload and encrypt a file          |
| `GET`    | `/api/files`                                | List all stored files              |
| `DELETE` | `/api/files/{file_id}`                      | Permanently delete a file          |
| `POST`   | `/api/reveal/start/{file_id}`               | Mint a session token               |
| `GET`    | `/api/reveal/chunk/{token}/{file_id}/{idx}` | Fetch and decrypt a single chunk   |
| `DELETE` | `/api/reveal/end/{token}`                   | Revoke a session token             |
| `GET`    | `/api/files/{file_id}/analysis`             | Get AI analysis result             |

---

## AI Models Used (all open-source, run locally)

| Model                                      | Task                    | Size    |
|--------------------------------------------|-------------------------|---------|
| `openai/whisper-base`                      | Audio transcription     | ~150 MB |
| `cardiffnlp/twitter-roberta-base-sentiment`| Sentiment analysis      | ~500 MB |
| `Salesforce/blip-image-captioning-base`    | Image captioning        | ~900 MB |
| `ultralytics/yolov8n`                      | Object detection        | ~6 MB   |
| `sshleifer/distilbart-cnn-12-6`            | Text summarization      | ~900 MB |
| `spacy/en_core_web_sm`                     | Named entity recognition| ~12 MB  |

---

## Environment Variables

| Variable           | Default    | Description                  |
|--------------------|------------|------------------------------|
| `CHUNK_SIZE`       | `65536`    | Chunk size in bytes (64 KB)  |
| `TOKEN_TTL`        | `30`       | Session token TTL in seconds |
| `MAX_UPLOAD_BYTES` | `52428800` | Max upload size (50 MB)      |
| `DATA_DIR`         | `data`     | Root directory for storage   |
