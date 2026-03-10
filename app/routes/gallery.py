import base64
import json
import os

from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse
from fastapi import templating

router = APIRouter(prefix="", tags=["gallery"])

PHOTOS_PER_PAGE = 50


def get_session(request: Request) -> dict:
    session_cookie = request.cookies.get("session", "")
    if session_cookie:
        try:
            decoded = base64.b64decode(session_cookie).decode()
            return json.loads(decoded)
        except:
            pass
    return {}


def load_config():
    with open("config.json") as f:
        return json.load(f)


@router.get("/gallery")
async def gallery(request: Request, tag: str = None, page: int = 1, error: str = None, success: str = None):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return RedirectResponse(f"/login?redirect=/gallery", status_code=302)
    
    config = load_config()
    
    from app.database import SessionLocal
    from app.models import Photo, Tag
    
    db = SessionLocal()
    
    base_query = db.query(Photo)
    if tag:
        base_query = base_query.join(Photo.tags).filter(Tag.label == tag)
    
    total_photos = base_query.count()
    total_pages = (total_photos + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE
    
    photos = base_query.order_by(Photo.upload_timestamp.desc())\
        .offset((page - 1) * PHOTOS_PER_PAGE)\
        .limit(PHOTOS_PER_PAGE)\
        .all()
    
    tags = db.query(Tag).all()
    
    photo_list = []
    for p in photos:
        photo_list.append({
            "id": p.id,
            "thumbnail_path": "/" + p.thumbnail_path if p.thumbnail_path else None,
            "original_filename": p.original_filename,
            "upload_timestamp": p.upload_timestamp.isoformat() if p.upload_timestamp else None,
            "tags": [t.label for t in p.tags]
        })
    
    db.close()
    
    return templates.TemplateResponse("gallery.html", {
        "request": {},
        "current_path": "/gallery",
        "photos": photo_list,
        "tags": [{"label": t.label} for t in tags],
        "selected_tag": tag,
        "current_page": page,
        "total_pages": total_pages,
        "total_photos": total_photos,
        "app_title": config.get("app_title", "PartyPix"),
        "is_admin": session.get("role") == "admin",
        "error": error,
        "success": success
    })


@router.get("/api/photos")
async def api_photos(request: Request, tag: str = None, page: int = 1):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import Photo, Tag
    
    db = SessionLocal()
    query = db.query(Photo)
    if tag:
        query = query.join(Photo.tags).filter(Tag.label == tag)
    
    total = query.count()
    photos = query.order_by(Photo.upload_timestamp.desc())\
        .offset((page - 1) * PHOTOS_PER_PAGE)\
        .limit(PHOTOS_PER_PAGE)\
        .all()
    
    result = []
    for p in photos:
        result.append({
            "id": p.id,
            "thumbnail": "/" + p.thumbnail_path if p.thumbnail_path else None,
            "full": f"/api/photos/{p.id}/full",
            "tags": [t.label for t in p.tags]
        })
    
    db.close()
    return {
        "photos": result,
        "page": page,
        "total_pages": (total + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE,
        "total": total
    }


@router.get("/api/photos/{photo_id}/full")
async def get_full_photo(photo_id: str):
    from app.database import SessionLocal
    from app.models import Photo
    
    db = SessionLocal()
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    db.close()
    
    if not photo:
        return {"error": "not found"}
    
    from fastapi.responses import FileResponse
    return FileResponse(photo.storage_path, media_type="image/jpeg")


def create_templates():
    def range_func(start, stop):
        return range(start, stop)
    
    env = templating.Jinja2Templates(directory="templates")
    env.env.globals['range'] = range_func
    return env

templates = create_templates()
