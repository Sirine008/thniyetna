from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from shared.auth import get_current_user
from shared.storage import save_stream

router = APIRouter()


@router.post("/image")
async def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(415, "Expected an image")
    key, _, public_url = save_stream(file.file, "images", file.filename)
    return {
        "media_uri": public_url,
        "storage_key": key,
        "content_type": file.content_type or "application/octet-stream",
        "owner_role": user["role"],
    }


@router.post("/video")
async def upload_video(file: UploadFile = File(...), user=Depends(get_current_user)):
    if file.content_type and not file.content_type.startswith("video/"):
        raise HTTPException(415, "Expected a video")
    key, _, public_url = save_stream(file.file, "videos", file.filename)
    return {
        "media_uri": public_url,
        "storage_key": key,
        "content_type": file.content_type or "application/octet-stream",
        "owner_role": user["role"],
    }
