import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    # Chunk size in bytes (64 KB default)
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", 65536))

    # Root data directory
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data"))

    # Subdirectory for encrypted chunks and manifests
    FILES_DIR: Path = Path(os.getenv("DATA_DIR", "data")) / "files"

    # Subdirectory for per-file AES keys (physically separated from chunks)
    KEYS_DIR: Path = Path(os.getenv("DATA_DIR", "data")) / "keys"

    # Reveal session token TTL in seconds
    TOKEN_TTL: int = int(os.getenv("TOKEN_TTL", 30))

    # Allowed MIME types
    ALLOWED_MIME_TYPES: tuple = (
        "text/plain",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "video/mp4",
        "video/webm",
        "video/ogg",
    )

    # Maximum upload size in bytes (50 MB)
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", 52428800))


settings = Settings()

# Create storage directories at import time
settings.FILES_DIR.mkdir(parents=True, exist_ok=True)
settings.KEYS_DIR.mkdir(parents=True, exist_ok=True)
