import asyncio

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.logger import get_logger
from app.storage import save_analysis, store_file

router = APIRouter(tags=["upload"])
log    = get_logger("upload")


def _run_analysis(file_id: str, raw_bytes: bytes, mime_type: str) -> None:
    """
    Synchronous background task: run the LangGraph pipeline and persist results.
    Executed in FastAPI's BackgroundTasks thread pool after the response is sent.
    """
    from app.agents.orchestrator import run_analysis
    fid = file_id[:8]
    log.info(f"[{fid}] Background analysis started")
    try:
        result           = run_analysis(file_id, raw_bytes, mime_type)
        result["status"] = "complete"
        save_analysis(file_id, result)

        # ── Summary of what was saved ─────────────────────────────────────────
        t = result.get("type", "unknown")
        log.info(f"[{fid}] ── Analysis result summary (type={t}) ──────────────")
        if t == "text":
            log.info(f"[{fid}]   word_count  : {result.get('word_count')}")
            log.info(f"[{fid}]   summary     : {str(result.get('summary','–'))[:100]}")
            ents = result.get("entities", {})
            log.info(f"[{fid}]   entities    : {sum(len(v) for v in ents.values())} across {len(ents)} types")
        elif t == "audio":
            log.info(f"[{fid}]   language    : {result.get('language')}")
            log.info(f"[{fid}]   sentiment   : {result.get('sentiment')}")
            tr = result.get("transcript", "") or ""
            log.info(f"[{fid}]   transcript  : \"{tr[:100]}{'...' if len(tr)>100 else ''}\"")
        elif t == "image":
            log.info(f"[{fid}]   image_size  : {result.get('image_size')}")
            log.info(f"[{fid}]   caption     : \"{result.get('caption')}\"")
            ocr_summary = f"{len(result['ocr_text'])} chars" if result.get('ocr_text') else 'none'
            log.info(f"[{fid}]   ocr_text    : {ocr_summary}")
            log.info(f"[{fid}]   detections  : {[d['object'] for d in result.get('detections', [])]}")
        elif t == "video":
            log.info(f"[{fid}]   duration    : {result.get('duration_seconds')}s")
            log.info(f"[{fid}]   frames      : {result.get('frames_analyzed')}")
            log.info(f"[{fid}]   captions    : {result.get('scene_captions')}")
            log.info(f"[{fid}]   detections  : {[d['object'] for d in result.get('detections', [])]}")
            audio = result.get("audio") or {}
            log.info(f"[{fid}]   transcript  : \"{str(audio.get('transcript','–'))[:80]}\"")
        log.info(f"[{fid}] ─────────────────────────────────────────────────────")
    except Exception as exc:
        log.error(f"[{fid}] Analysis pipeline failed: {exc}", exc_info=True)
        save_analysis(file_id, {"status": "failed", "error": str(exc)})


@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> JSONResponse:
    """
    Accept a multipart file upload, encrypt it in chunks, and store on disk.
    Kicks off an AI analysis pipeline as a background task after storing.
    """
    log.info(f"Received upload request: {file.filename!r} ({file.content_type})")

    if file.content_type not in settings.ALLOWED_MIME_TYPES:
        log.warning(f"Rejected unsupported MIME type: {file.content_type}")
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported media type '{file.content_type}'. "
                f"Allowed: {list(settings.ALLOWED_MIME_TYPES)}"
            ),
        )

    data = await file.read()
    size_mb = len(data) / 1024 / 1024
    log.info(f"Read {size_mb:.2f} MB from {file.filename!r}")

    if len(data) > settings.MAX_UPLOAD_BYTES:
        log.warning(f"Rejected oversized file: {size_mb:.1f} MB")
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum: {settings.MAX_UPLOAD_BYTES} bytes.",
        )

    file_id = await asyncio.to_thread(
        store_file, data, file.filename or "unnamed", file.content_type,
    )
    log.info(f"[{file_id[:8]}] Stored {file.filename!r} as file_id={file_id}")

    await asyncio.to_thread(save_analysis, file_id, {"status": "pending"})
    log.info(f"[{file_id[:8]}] Analysis status set to pending, queuing background task...")

    background_tasks.add_task(_run_analysis, file_id, data, file.content_type)
    log.info(f"[{file_id[:8]}] Background analysis task queued")

    return JSONResponse(
        status_code=201,
        content={"file_id": file_id, "original_filename": file.filename},
    )
