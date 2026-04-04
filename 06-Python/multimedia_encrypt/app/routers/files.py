import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.storage import delete_file, file_exists, list_manifests

router = APIRouter(tags=["files"])


@router.get("/files")
async def list_files() -> JSONResponse:
    """
    Return metadata for all stored files.
    Never returns key material — manifests contain only structural metadata.
    """
    manifests = await asyncio.to_thread(list_manifests)
    return JSONResponse(content={"files": manifests})


@router.delete("/files/{file_id}")
async def remove_file(file_id: str) -> JSONResponse:
    """
    Permanently delete all chunks, manifest, and key for a file.

    Returns:
        200 { status: "deleted" }
        404 if file_id does not exist
    """
    exists = await asyncio.to_thread(file_exists, file_id)
    if not exists:
        raise HTTPException(status_code=404, detail="File not found.")
    await asyncio.to_thread(delete_file, file_id)
    return JSONResponse(content={"status": "deleted"})
