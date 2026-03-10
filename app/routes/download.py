import base64
import io
import json
import zipfile

from fastapi import APIRouter, Request, Form
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="", tags=["download"])


def get_session(request: Request) -> dict:
    session_cookie = request.cookies.get("session", "")
    if session_cookie:
        try:
            decoded = base64.b64decode(session_cookie).decode()
            return json.loads(decoded)
        except:
            pass
    return {}


@router.post("/download")
async def download_photos(request: Request, photo_ids: str = Form(...)):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return {"error": "unauthorized"}
    
    photo_id_list = [pid.strip() for pid in photo_ids.split(",") if pid.strip()]
    
    if not photo_id_list:
        return {"error": "no photos selected"}
    
    from app.database import SessionLocal
    from app.models import Photo
    
    db = SessionLocal()
    photos = db.query(Photo).filter(Photo.id.in_(photo_id_list)).all()
    db.close()
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            if os.path.exists(photo.storage_path):
                zf.write(photo.storage_path, photo.original_filename)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=party_photos.zip"}
    )


import os
