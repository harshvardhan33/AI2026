import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.crypto import generate_key, encrypt_chunk, decrypt_chunk


# ── Path helpers ──────────────────────────────────────────────────────────────

def _file_dir(file_id: str) -> Path:
    return settings.FILES_DIR / file_id


def _chunks_dir(file_id: str) -> Path:
    return _file_dir(file_id) / "chunks"


def _manifest_path(file_id: str) -> Path:
    return _file_dir(file_id) / "manifest.json"


def _key_path(file_id: str) -> Path:
    # Keys live in a separate directory, never alongside chunks
    return settings.KEYS_DIR / f"{file_id}.key"


def _chunk_path(file_id: str, index: int) -> Path:
    return _chunks_dir(file_id) / f"{index}.enc"


# ── Write operations ──────────────────────────────────────────────────────────

def store_file(data: bytes, original_name: str, mime_type: str) -> str:
    """
    Split data into fixed-size chunks, encrypt each with AES-256-GCM,
    and persist everything to disk. Returns the new file_id (UUID4 string).

    Manifest structure stored at data/files/{file_id}/manifest.json:
    {
      "file_id": str,
      "original_filename": str,
      "media_type": "text" | "image",
      "mime_type": str,
      "chunk_size": int,
      "total_chunks": int,
      "total_bytes": int,
      "created_at": str  (ISO 8601)
    }
    """
    file_id = str(uuid.uuid4())
    key = generate_key()

    _chunks_dir(file_id).mkdir(parents=True, exist_ok=True)

    chunk_size = settings.CHUNK_SIZE
    chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
    if not chunks:
        chunks = [b""]  # handle zero-byte files

    for idx, chunk in enumerate(chunks):
        encrypted = encrypt_chunk(key, chunk)
        _chunk_path(file_id, idx).write_bytes(encrypted)

    # Write key separately — never colocated with chunks
    _key_path(file_id).write_bytes(key)

    # Derive coarse media_type for the manifest
    if mime_type.startswith("image/"):
        media_type = "image"
    elif mime_type.startswith("audio/"):
        media_type = "audio"
    elif mime_type.startswith("video/"):
        media_type = "video"
    else:
        media_type = "text"

    manifest: dict[str, Any] = {
        "file_id": file_id,
        "original_filename": original_name,
        "media_type": media_type,
        "mime_type": mime_type,
        "chunk_size": chunk_size,
        "total_chunks": len(chunks),
        "total_bytes": len(data),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _manifest_path(file_id).write_text(json.dumps(manifest, indent=2))

    return file_id


# ── Read operations ───────────────────────────────────────────────────────────

def read_manifest(file_id: str) -> dict:
    path = _manifest_path(file_id)
    if not path.exists():
        raise FileNotFoundError(f"No manifest for file_id={file_id}")
    return json.loads(path.read_text())


def read_chunk_decrypted(file_id: str, chunk_index: int) -> bytes:
    """Read and decrypt a single chunk. Raises InvalidTag on tampering."""
    key = _key_path(file_id).read_bytes()
    blob = _chunk_path(file_id, chunk_index).read_bytes()
    return decrypt_chunk(key, blob)


def list_manifests() -> list[dict]:
    """Return all manifests sorted by creation time (newest first).
    Never returns key material."""
    if not settings.FILES_DIR.exists():
        return []
    manifests = []
    for file_dir in settings.FILES_DIR.iterdir():
        manifest_path = file_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifests.append(json.loads(manifest_path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
    manifests.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return manifests


def file_exists(file_id: str) -> bool:
    return _manifest_path(file_id).exists()


def chunk_exists(file_id: str, chunk_index: int) -> bool:
    return _chunk_path(file_id, chunk_index).exists()


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _analysis_path(file_id: str) -> Path:
    return _file_dir(file_id) / "analysis.json"


def save_analysis(file_id: str, data: dict) -> None:
    """Atomically write analysis.json via a temp-file swap."""
    target = _analysis_path(file_id)
    tmp    = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, target)


def load_analysis(file_id: str) -> dict:
    path = _analysis_path(file_id)
    if not path.exists():
        return {"status": "pending"}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"status": "pending"}


def delete_file(file_id: str) -> None:
    """Delete all chunks, manifest, and key for a given file_id."""
    import shutil
    file_dir = _file_dir(file_id)
    if file_dir.exists():
        shutil.rmtree(file_dir)
    key = _key_path(file_id)
    if key.exists():
        key.unlink()
