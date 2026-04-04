"""
Video Crew
──────────
• Keyframe extraction         — OpenCV  (1 frame every 5 s, max 5 frames)
• Contextual scene captions   — BLIP via image_crew (LLM per keyframe)
• Object detection            — YOLO via image_crew
• Audio transcription         — Whisper via audio_crew
• Sentiment on audio          — CardiffNLP via audio_crew

Requires: ffmpeg on PATH for moviepy audio extraction and Whisper.
"""
from __future__ import annotations

import io
import os
import tempfile
import time

import cv2
from PIL import Image

from app.logger import get_logger

log = get_logger("video_crew")


def run(raw_bytes: bytes, mime_type: str, file_id: str = "") -> dict:
    fid      = file_id[:8]
    ext      = {"video/mp4": ".mp4", "video/webm": ".webm", "video/ogg": ".ogv"}.get(mime_type, ".mp4")
    t_total  = time.perf_counter()
    log.info(f"[{fid}] video_crew: {len(raw_bytes)/1024/1024:.1f} MB, mime={mime_type}")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(raw_bytes)
        tmp_path = f.name

    audio_tmp = None
    try:
        # ── Keyframe extraction ───────────────────────────────────────────────
        log.info(f"[{fid}] Extracting keyframes with OpenCV...")
        t0 = time.perf_counter()
        cap          = cv2.VideoCapture(tmp_path)
        fps          = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration     = round(total_frames / fps, 1) if fps > 0 else 0.0
        interval     = max(1, int(fps * 5))

        keyframe_bufs: list[bytes] = []
        frame_idx = 0

        while cap.isOpened() and len(keyframe_bufs) < 5:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % interval == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                buf = io.BytesIO()
                Image.fromarray(rgb).save(buf, format="JPEG")
                keyframe_bufs.append(buf.getvalue())
            frame_idx += 1
        cap.release()
        ms = (time.perf_counter() - t0) * 1000
        log.info(f"[{fid}] Keyframe extraction complete in {ms:.0f}ms — "
                 f"{len(keyframe_bufs)} frame(s) from {duration}s video ({fps:.1f} fps)")

        # ── Analyse keyframes (image crew: YOLO + BLIP) ───────────────────────
        from app.agents.image_crew import run as image_run

        all_objects:      dict[str, float] = {}
        ocr_parts:        list[str]        = []
        scene_captions:   list[str]        = []

        for i, kf in enumerate(keyframe_bufs):
            log.info(f"[{fid}] Analysing keyframe {i+1}/{len(keyframe_bufs)}...")
            try:
                r = image_run(kf, "image/jpeg", file_id)
                for det in r.get("detections", []):
                    obj, conf = det["object"], det["confidence"]
                    if conf > all_objects.get(obj, 0.0):
                        all_objects[obj] = conf
                if r.get("ocr_text"):
                    ocr_parts.append(r["ocr_text"])
                if r.get("caption"):
                    scene_captions.append(r["caption"])
                    log.info(f"[{fid}] Frame {i+1} caption: {r['caption']!r}")
            except Exception as exc:
                log.warning(f"[{fid}] Keyframe {i+1} analysis failed: {exc}")

        detections = [
            {"object": k, "confidence": round(v, 3)}
            for k, v in all_objects.items()
        ]
        ocr_text = " ".join(ocr_parts).strip() or None
        objs = [d['object'] for d in detections]
        log.info(f"[{fid}] Keyframe analysis done — objects: {objs}, "
                 f"{len(scene_captions)} scene caption(s): {scene_captions}")

        # ── Audio extraction ──────────────────────────────────────────────────
        audio_result = None
        try:
            log.info(f"[{fid}] Extracting audio track with moviepy...")
            t0 = time.perf_counter()
            from moviepy import VideoFileClip
            clip = VideoFileClip(tmp_path)
            if clip.audio is not None:
                audio_tmp = tmp_path + ".wav"
                clip.audio.write_audiofile(audio_tmp, logger=None)
                clip.close()
                ms = (time.perf_counter() - t0) * 1000
                log.info(f"[{fid}] Audio extracted in {ms:.0f}ms, running audio_crew...")
                with open(audio_tmp, "rb") as af:
                    audio_bytes = af.read()
                from app.agents.audio_crew import run as audio_run
                audio_result = audio_run(audio_bytes, "audio/wav", file_id)
            else:
                clip.close()
                log.info(f"[{fid}] No audio track found in video")
        except Exception as exc:
            log.warning(f"[{fid}] Audio extraction failed: {exc}")

        total_ms = (time.perf_counter() - t_total) * 1000
        log.info(f"[{fid}] video_crew total time: {total_ms:.0f}ms")

        return {
            "type":              "video",
            "duration_seconds":  duration,
            "frames_analyzed":   len(keyframe_bufs),
            "scene_captions":    scene_captions,
            "detections":        detections,
            "ocr_text":          ocr_text,
            "audio":             audio_result,
        }
    finally:
        os.unlink(tmp_path)
        if audio_tmp and os.path.exists(audio_tmp):
            os.unlink(audio_tmp)
