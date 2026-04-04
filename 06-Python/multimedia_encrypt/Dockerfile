# ── Build stage: install dependencies ────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# System dependencies required at build time
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only PyTorch first to avoid pulling the ~2 GB CUDA variant,
# then install the rest of the requirements (torch line will already be satisfied)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Download spaCy English model into the venv (no network at runtime needed)
RUN python -m spacy download en_core_web_sm


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Runtime system dependencies
# - ffmpeg:           required by Whisper (audio decoding) and moviepy (video)
# - tesseract-ocr:    required by pytesseract (OCR on images)
# - libgl1 / libglib2.0-0: required by OpenCV on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY app/    ./app/
COPY static/ ./static/

# Create runtime directories (data is mounted as a volume in production)
RUN mkdir -p data/files data/keys logs

# Hugging Face and Ultralytics model caches live under /root by default.
# Pre-warm them here if you want zero-latency first requests (adds ~2 GB to image).
# Uncomment the lines below to pre-download all models at build time:
# RUN python -c "import whisper; whisper.load_model('base')"
# RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
# RUN python -c "from transformers import BlipProcessor, BlipForConditionalGeneration; \
#     BlipProcessor.from_pretrained('Salesforce/blip-image-captioning-base'); \
#     BlipForConditionalGeneration.from_pretrained('Salesforce/blip-image-captioning-base')"
# RUN python -c "from transformers import pipeline; \
#     pipeline('summarization', model='sshleifer/distilbart-cnn-12-6', device=-1)"
# RUN python -c "from transformers import pipeline; \
#     pipeline('text-classification', model='cardiffnlp/twitter-roberta-base-sentiment', device=-1)"

EXPOSE 9000

# Mount data/ as a volume to persist encrypted files and keys across restarts:
#   docker run -v $(pwd)/data:/app/data ...
VOLUME ["/app/data", "/app/logs"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
