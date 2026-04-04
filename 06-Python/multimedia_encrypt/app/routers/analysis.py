import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.storage import file_exists, load_analysis

router = APIRouter(tags=["analysis"])
log    = get_logger("analysis")


@router.get("/files/{file_id}/analysis")
async def get_analysis(file_id: str) -> JSONResponse:
    """
    Return the AI analysis result for a stored file.

    Returns:
        200 { status: "pending" }                    — analysis still running
        200 { status: "complete", type, ...fields }  — analysis done
        200 { status: "failed",   error: str }       — analysis errored
        404 if file_id does not exist
    """
    log.debug(f"[{file_id[:8]}] Analysis result requested")
    exists = await asyncio.to_thread(file_exists, file_id)
    if not exists:
        log.warning(f"[{file_id[:8]}] Analysis requested for unknown file")
        raise HTTPException(status_code=404, detail="File not found.")

    result = await asyncio.to_thread(load_analysis, file_id)
    status = result.get("status", "unknown")
    log.info(f"[{file_id[:8]}] Analysis status={status} returned")

    if status == "complete":
        t = result.get("type", "?")
        fields = [k for k in result if k not in ("status", "type")]
        non_null = [k for k in fields if result[k] not in (None, [], {}, "")]
        log.info(f"[{file_id[:8]}]   type={t}, populated fields: {non_null}")

    return JSONResponse(content=result)
