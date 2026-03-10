import base64
import json
import os
import uuid

from typing import Union

from fastapi import APIRouter, Request, UploadFile, Form, Response
from fastapi.responses import RedirectResponse

from app.auth import verify_password, load_config

router = APIRouter(prefix="", tags=["upload"])


@router.post("/login")
async def login(request: Request, password: str = Form(...), redirect: str = Form("/gallery")):
    config = load_config()
    
    if verify_password(password, config["guest_password_hash"]):
        session_data = json.dumps({"role": "guest"})
        encoded = base64.b64encode(session_data.encode()).decode()
        response = RedirectResponse(redirect, status_code=302)
        response.set_cookie("session", encoded, httponly=True, samesite="lax")
        return response
    
    if verify_password(password, config["admin_password_hash"]):
        session_data = json.dumps({"role": "admin"})
        encoded = base64.b64encode(session_data.encode()).decode()
        response = RedirectResponse("/admin", status_code=302)
        response.set_cookie("session", encoded, httponly=True, samesite="lax")
        return response
    
    return templates.TemplateResponse("login.html", {"request": {}, "error": "Invalid password", "redirect": redirect})


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


def get_session(request: Request) -> dict:
    session_cookie = request.cookies.get("session", "")
    if session_cookie:
        try:
            decoded = base64.b64decode(session_cookie).decode()
            return json.loads(decoded)
        except:
            pass
    return {}


async def save_photo(file: UploadFile) -> bool:
    if not file.content_type or not file.content_type.startswith("image/"):
        return False
    
    content = await file.read()
    
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    if ext.lower() not in ["jpg", "jpeg", "png", "gif", "webp"]:
        ext = "jpg"
    
    photo_id = str(uuid.uuid4())
    filename = f"{photo_id}.{ext}"
    storage_path = f"storage/photos/{filename}"
    thumbnail_path = f"storage/thumbnails/{photo_id}.jpg"
    
    with open(storage_path, "wb") as f:
        f.write(content)
    
    from PIL import Image
    img = Image.open(storage_path)
    img.thumbnail((300, 300), Image.LANCZOS)
    img.save(thumbnail_path, "JPEG", quality=80)
    
    from app.database import SessionLocal
    from app.models import Photo
    
    db = SessionLocal()
    photo = Photo(
        id=photo_id,
        filename=filename,
        original_filename=file.filename or "photo",
        storage_path=storage_path,
        thumbnail_path=thumbnail_path
    )
    db.add(photo)
    db.commit()
    db.close()
    
    return True


@router.get("/upload")
async def upload_page(request: Request):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return RedirectResponse(f"/login?redirect=/upload", status_code=302)
    
    config = load_config()
    
    return templates.TemplateResponse("upload.html", {
        "request": {},
        "current_path": "/upload",
        "app_title": config.get("app_title", "PartyPix"),
        "is_admin": session.get("role") == "admin"
    })


@router.post("/upload")
async def upload_photos(request: Request, files: Union[list[UploadFile], None] = None):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return RedirectResponse("/login", status_code=302)
    
    if not files:
        return RedirectResponse("/gallery?error=no_files", status_code=302)
    
    for file in files:
        await save_photo(file)
    
    return RedirectResponse("/gallery?success=uploaded", status_code=302)


from fastapi import templating
templates = templating.Jinja2Templates(directory="templates")
