# Encrypted Multimedia Vault

A privacy-first file storage system built with FastAPI. Files are encrypted at rest using **AES-256-GCM** and decrypted only on demand via a hold-to-reveal mechanism — the moment you release, all content is wiped from the browser.

## Features

- AES-256-GCM encryption with a unique key and nonce per file
- Files split into 64KB chunks — each chunk encrypted independently
- Keys stored physically separate from encrypted chunks
- Short-lived session tokens (30s TTL) for reveal authorization
- Hold-to-reveal UI — release the button and content is instantly wiped
- Supports text, images, audio, and video
- Delete files permanently from the vault

## Supported File Types

| Type | Formats |
|------|---------|
| Text | `.txt` |
| Image | `.jpg`, `.png`, `.gif`, `.webp` |
| Audio | `.mp3`, `.ogg`, `.wav`, `.webm` |
| Video | `.mp4`, `.webm`, `.ogv` |

## Project Structure

```
multimedia_encrypt/
├── app/
│   ├── config.py        # Settings: chunk size, TTL, MIME allowlist, paths
│   ├── crypto.py        # AES-256-GCM encrypt/decrypt
│   ├── storage.py       # Chunking, manifest, key storage, delete
│   ├── sessions.py      # In-memory session token store with TTL sweep
│   ├── main.py          # FastAPI app entry point
│   └── routers/
│       ├── upload.py    # POST /api/upload
│       ├── files.py     # GET /api/files, DELETE /api/files/{file_id}
│       └── reveal.py    # POST/GET/DELETE /api/reveal/*
├── static/
│   ├── index.html
│   ├── app.js           # Hold-to-reveal logic, chunk streaming
│   └── style.css
├── data/                # Runtime storage (gitignored)
│   ├── files/           # Encrypted chunks + manifests
│   └── keys/            # AES keys (never colocated with chunks)
├── requirements.txt
└── README.md
```

## Setup & Run

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload --port 9000
```

Open `http://127.0.0.1:9000` in your browser.

Interactive API docs available at `http://127.0.0.1:9000/docs`.

## How It Works

### Upload
1. File is read and split into 64KB chunks
2. A unique AES-256-GCM key is generated per file
3. Each chunk is encrypted with a fresh random nonce
4. Encrypted chunks saved to `data/files/<file_id>/chunks/`
5. Key saved separately to `data/keys/<file_id>.key`
6. A manifest (metadata JSON) saved alongside the chunks

### Reveal
1. Client requests a session token (`POST /api/reveal/start/<file_id>`)
2. Token is valid for 30 seconds and bound to that specific file
3. Client fetches each chunk (`GET /api/reveal/chunk/<token>/<file_id>/<index>`)
4. Server decrypts each chunk on the fly and returns raw bytes
5. Browser reassembles chunks into a Blob and renders the content
6. On release, DOM is wiped and the token is revoked server-side

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload and encrypt a file |
| `GET` | `/api/files` | List all stored files |
| `DELETE` | `/api/files/{file_id}` | Permanently delete a file |
| `POST` | `/api/reveal/start/{file_id}` | Mint a session token |
| `GET` | `/api/reveal/chunk/{token}/{file_id}/{index}` | Fetch a decrypted chunk |
| `DELETE` | `/api/reveal/end/{token}` | Revoke a session token |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | `65536` | Chunk size in bytes (64KB) |
| `TOKEN_TTL` | `30` | Session token TTL in seconds |
| `MAX_UPLOAD_BYTES` | `52428800` | Max upload size (50MB) |
| `DATA_DIR` | `data` | Root directory for storage |
