import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.storage import store_file

router = APIRouter(tags=["upload"])


@router.post("/upload", status_code=201)
async def upload_file(file: UploadFile = File(...)) -> JSONResponse:
    """
    Accept a multipart file upload, encrypt it in chunks, and store on disk.

    Returns:
        201 { file_id, original_filename }
        415 if MIME type is not allowed
        413 if file exceeds MAX_UPLOAD_BYTES
    """
    # Validate MIME type (content_type from multipart header, not extension)
    print("Check this : ",file.content_type)
    if file.content_type not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported media type '{file.content_type}'. "
                f"Allowed: {list(settings.ALLOWED_MIME_TYPES)}"
            ),
        )

    data = await file.read()

    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum: {settings.MAX_UPLOAD_BYTES} bytes.",
        )

    # Offload blocking disk I/O (chunking, encryption, writes) to thread pool
    file_id = await asyncio.to_thread(
        store_file,
        data,
        file.filename or "unnamed",
        file.content_type,
    )

    return JSONResponse(
        status_code=201,
        content={"file_id": file_id, "original_filename": file.filename},
    )
