import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user_id
from app.config import settings

router = APIRouter(prefix="/v1/upload", tags=["upload"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    _user_id: str = Depends(get_current_user_id),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Use PNG, JPG, GIF, or WebP.")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "File too large (max 5 MB)")

    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "png"
    filename = f"{uuid.uuid4().hex}.{ext}"

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(data)

    image_url = f"{settings.metadata_base_url}/uploads/{filename}"
    return JSONResponse({"url": image_url, "filename": filename})
