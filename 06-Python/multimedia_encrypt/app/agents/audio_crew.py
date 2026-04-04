"""
Audio Crew
──────────
• Transcription — OpenAI Whisper "base" (local, no API key)
• Sentiment     — cardiffnlp/twitter-roberta-base-sentiment

Requires: ffmpeg on system PATH.
"""
from __future__ import annotations

import os
import tempfile
import time

from app.logger import get_logger

log = get_logger("audio_crew")

_whisper_model  = None
_sentiment_pipe = None

_EXT_MAP = {
    "audio/mpeg": ".mp3",
    "audio/wav":  ".wav",
    "audio/ogg":  ".ogg",
    "audio/webm": ".webm",
}
_LABEL_MAP = {"LABEL_0": "negative", "LABEL_1": "neutral", "LABEL_2": "positive"}


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        log.info("Loading Whisper 'base' model (first use — may download ~150 MB)...")
        _whisper_model = whisper.load_model("base")
        log.info("Whisper model loaded")
    return _whisper_model


def _get_sentiment():
    global _sentiment_pipe
    if _sentiment_pipe is None:
        from transformers import pipeline
        log.info("Loading CardiffNLP sentiment model (first use)...")
        _sentiment_pipe = pipeline(
            "text-classification",
            model="cardiffnlp/twitter-roberta-base-sentiment",
            device=-1,
        )
        log.info("Sentiment model loaded")
    return _sentiment_pipe


def run(raw_bytes: bytes, mime_type: str, file_id: str = "") -> dict:
    fid    = file_id[:8]
    suffix = _EXT_MAP.get(mime_type, ".wav")
    log.info(f"[{fid}] audio_crew: {len(raw_bytes)/1024:.1f} KB, mime={mime_type}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw_bytes)
        tmp_path = f.name

    try:
        log.info(f"[{fid}] Transcribing with Whisper...")
        t0     = time.perf_counter()
        model  = _get_whisper()
        result = model.transcribe(tmp_path, fp16=False)
        ms     = (time.perf_counter() - t0) * 1000
        transcript = result["text"].strip()
        language   = result.get("language", "unknown")
        log.info(f"[{fid}] Whisper transcription complete in {ms:.0f}ms "
                 f"(lang={language}): \"{transcript[:80]}{'...' if len(transcript)>80 else ''}\"" )
    except FileNotFoundError:
        log.error(f"[{fid}] ffmpeg not found on PATH — cannot transcribe audio")
        return {
            "type": "audio", "transcript": None, "language": None,
            "sentiment": None,
            "error": "ffmpeg not found on PATH — install ffmpeg to enable transcription",
        }
    finally:
        os.unlink(tmp_path)

    sentiment = None
    if transcript:
        log.info(f"[{fid}] Running sentiment analysis...")
        try:
            t0    = time.perf_counter()
            out   = _get_sentiment()(transcript[:512])[0]
            ms    = (time.perf_counter() - t0) * 1000
            label = _LABEL_MAP.get(out["label"], out["label"])
            sentiment = {"label": label, "score": round(out["score"], 3)}
            log.info(f"[{fid}] Sentiment complete in {ms:.0f}ms: {label} ({sentiment['score']:.2f})")
        except Exception as exc:
            log.warning(f"[{fid}] Sentiment failed: {exc}")

    return {
        "type":       "audio",
        "transcript": transcript,
        "language":   language,
        "sentiment":  sentiment,
    }
