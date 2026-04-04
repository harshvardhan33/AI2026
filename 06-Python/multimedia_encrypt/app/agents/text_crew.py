"""
Text Crew
─────────
• Named Entity Recognition — spaCy en_core_web_sm
• Summarization            — sshleifer/distilbart-cnn-12-6
"""
from __future__ import annotations

import time

from app.logger import get_logger

log = get_logger("text_crew")

_nlp        = None
_summarizer = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        log.info("Loading spaCy model (en_core_web_sm)...")
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            log.info("Downloading en_core_web_sm...")
            import spacy.cli
            spacy.cli.download("en_core_web_sm")
            _nlp = spacy.load("en_core_web_sm")
        log.info("spaCy model loaded")
    return _nlp


def _get_summarizer():
    global _summarizer
    if _summarizer is None:
        from transformers import pipeline
        log.info("Loading DistilBART summarization model (first use — may download ~900 MB)...")
        _summarizer = pipeline(
            "summarization",
            model="sshleifer/distilbart-cnn-12-6",
            device=-1,
        )
        log.info("DistilBART loaded")
    return _summarizer


def run(raw_bytes: bytes, mime_type: str, file_id: str = "") -> dict:
    fid  = file_id[:8]
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    words = text.split()
    log.info(f"[{fid}] text_crew: {len(words)} words, {len(text)} chars")

    # ── NER ──────────────────────────────────────────────────────────────────
    nlp  = _get_nlp()
    t0   = time.perf_counter()
    doc  = nlp(text[:100_000])
    entities: dict[str, list[str]] = {}
    for ent in doc.ents:
        bucket = entities.setdefault(ent.label_, [])
        if ent.text not in bucket:
            bucket.append(ent.text)
    ms = (time.perf_counter() - t0) * 1000
    log.info(f"[{fid}] NER complete in {ms:.0f}ms — "
             f"{sum(len(v) for v in entities.values())} entities across {len(entities)} types")

    # ── Summarization ─────────────────────────────────────────────────────────
    summary = None
    if len(words) >= 60:
        log.info(f"[{fid}] Running summarization...")
        try:
            t0      = time.perf_counter()
            out     = _get_summarizer()(" ".join(words[:800]),
                                        max_length=130, min_length=30, do_sample=False)
            summary = out[0]["summary_text"]
            ms      = (time.perf_counter() - t0) * 1000
            log.info(f"[{fid}] Summarization complete in {ms:.0f}ms: \"{summary[:80]}...\"")
        except Exception as exc:
            log.warning(f"[{fid}] Summarization failed: {exc}")
    else:
        log.info(f"[{fid}] Text too short for summarization (<60 words)")

    return {
        "type":       "text",
        "word_count": len(words),
        "char_count": len(text),
        "entities":   entities,
        "summary":    summary,
    }
