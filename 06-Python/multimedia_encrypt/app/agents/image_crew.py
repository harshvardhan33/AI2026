"""
Image Crew
──────────
• OCR                    — pytesseract       (requires Tesseract binary on PATH)
• Object detection       — YOLOv8n           (ultralytics; auto-downloads ~6 MB)
• Contextual captioning  — BLIP base         (Salesforce; auto-downloads ~900 MB)
  Generates a natural-language description of the image using a vision-language model.
"""
from __future__ import annotations

import io
import time

from app.logger import get_logger

log = get_logger("image_crew")

_yolo           = None
_blip_processor = None
_blip_model     = None


def _get_yolo():
    global _yolo
    if _yolo is None:
        from ultralytics import YOLO
        log.info("Loading YOLOv8n model (first use — downloads ~6 MB if not cached)...")
        _yolo = YOLO("yolov8n.pt")
        log.info("YOLOv8n loaded")
    return _yolo


def _get_blip():
    global _blip_processor, _blip_model
    if _blip_model is None:
        import torch
        from transformers import BlipForConditionalGeneration, BlipProcessor
        log.info("Loading BLIP image-captioning model (first use — downloads ~900 MB)...")
        _blip_processor = BlipProcessor.from_pretrained(
            "Salesforce/blip-image-captioning-base"
        )
        _blip_model = BlipForConditionalGeneration.from_pretrained(
            "Salesforce/blip-image-captioning-base"
        )
        _blip_model.eval()
        log.info("BLIP model loaded")
    return _blip_processor, _blip_model


def _caption(image) -> str:
    """Generate a natural-language description of the image using BLIP."""
    import torch
    processor, model = _get_blip()
    inputs = processor(image, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=60)
    return processor.decode(out[0], skip_special_tokens=True)


def run(raw_bytes: bytes, mime_type: str = "image/jpeg", file_id: str = "") -> dict:
    import numpy as np
    from PIL import Image

    fid   = file_id[:8]
    image = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    log.info(f"[{fid}] image_crew: {image.size[0]}×{image.size[1]} px, mime={mime_type}")

    # ── OCR ───────────────────────────────────────────────────────────────────
    # ── OCR ───────────────────────────────────────────────────────────────────
    ocr_text = None
    try:
        import pytesseract
        # Point to the Windows default install path if not on system PATH
        pytesseract.pytesseract.tesseract_cmd = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        log.info(f"[{fid}] Running OCR...")
        t0  = time.perf_counter()
        raw = pytesseract.image_to_string(image).strip()
        ms  = (time.perf_counter() - t0) * 1000
        ocr_text = raw or None
        if raw:
            preview = raw[:120].replace("\n", " ")
            log.info(f"[{fid}] OCR complete in {ms:.0f}ms — {len(raw)} chars: \"{preview}{'...' if len(raw)>120 else ''}\"")
        else:
            log.info(f"[{fid}] OCR complete in {ms:.0f}ms — no text found")
    except Exception as exc:
        log.warning(f"[{fid}] OCR failed (Tesseract installed?): {exc}")

    # ── Object detection ──────────────────────────────────────────────────────
    detections: list[dict] = []
    try:
        log.info(f"[{fid}] Running YOLO object detection...")
        t0        = time.perf_counter()
        model     = _get_yolo()
        results   = model(np.array(image), verbose=False)
        ms        = (time.perf_counter() - t0) * 1000
        seen: set[str] = set()
        for r in results:
            for box in r.boxes:
                cls_name = model.names[int(box.cls[0])]
                conf     = float(box.conf[0])
                if conf >= 0.40 and cls_name not in seen:
                    detections.append({"object": cls_name, "confidence": round(conf, 3)})
                    seen.add(cls_name)
        if detections:
            objs = ", ".join(f"{d['object']}({d['confidence']:.2f})" for d in detections)
            log.info(f"[{fid}] YOLO complete in {ms:.0f}ms — detected: {objs}")
        else:
            log.info(f"[{fid}] YOLO complete in {ms:.0f}ms — no objects above 0.40 confidence")
    except Exception as exc:
        log.warning(f"[{fid}] YOLO failed: {exc}", exc_info=True)

    # ── BLIP contextual captioning ────────────────────────────────────────────
    caption = None
    try:
        log.info(f"[{fid}] Generating contextual caption with BLIP...")
        t0      = time.perf_counter()
        caption = _caption(image)
        ms      = (time.perf_counter() - t0) * 1000
        log.info(f"[{fid}] BLIP complete in {ms:.0f}ms — caption: \"{caption}\"")
    except Exception as exc:
        log.warning(f"[{fid}] BLIP captioning failed: {exc}", exc_info=True)

    return {
        "type":       "image",
        "image_size": list(image.size),
        "caption":    caption,
        "detections": detections,
        "ocr_text":   ocr_text,
    }
