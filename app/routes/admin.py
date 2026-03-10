import base64
import json
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/admin", tags=["admin"])

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


@router.get("")
async def admin_page(request: Request, page: int = 1, sort: str = "newest"):
    session = get_session(request)
    if session.get("role") != "admin":
        return RedirectResponse("/login?redirect=/admin", status_code=302)
    
    config = load_config()
    
    from app.database import SessionLocal
    from app.models import Photo, Tag
    
    db = SessionLocal()
    
    # Apply sorting
    if sort == "oldest":
        order = Photo.upload_timestamp.asc()
    elif sort == "alpha":
        order = Photo.original_filename.asc()
    else:  # newest
        order = Photo.upload_timestamp.desc()
    
    total_photos = db.query(Photo).count()
    total_pages = (total_photos + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE
    
    photos = db.query(Photo)\
        .order_by(order)\
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
            "tags": [{"id": t.id, "label": t.label} for t in p.tags]
        })
    
    db.close()
    
    return templates.TemplateResponse("admin.html", {
        "request": {},
        "current_path": "/admin",
        "photos": photo_list,
        "tags": [{"id": t.id, "label": t.label} for t in tags],
        "current_page": page,
        "total_pages": total_pages,
        "total_photos": total_photos,
        "current_sort": sort,
        "app_title": config.get("app_title", "PartyPix")
    })


@router.post("/photo/{photo_id}/delete")
async def delete_photo(request: Request, photo_id: str):
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import Photo
    
    db = SessionLocal()
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    
    if photo:
        if os.path.exists(photo.storage_path):
            os.remove(photo.storage_path)
        if photo.thumbnail_path and os.path.exists(photo.thumbnail_path):
            os.remove(photo.thumbnail_path)
        
        db.delete(photo)
        db.commit()
    
    db.close()
    
    return RedirectResponse("/admin", status_code=302)


@router.post("/tag")
async def create_tag(request: Request, label: str = Form(...)):
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    import uuid
    from app.database import SessionLocal
    from app.models import Tag
    
    db = SessionLocal()
    existing = db.query(Tag).filter(Tag.label == label).first()
    if not existing:
        tag = Tag(id=str(uuid.uuid4()), label=label)
        db.add(tag)
        db.commit()
    
    db.close()
    
    return RedirectResponse("/admin", status_code=302)


@router.post("/photo/{photo_id}/tag")
async def add_tag_to_photo(request: Request, photo_id: str, tag_id: str = Form(...)):
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import Photo, Tag, photo_tags
    
    db = SessionLocal()
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    
    if photo and tag:
        stmt = photo_tags.insert().values(photo_id=photo_id, tag_id=tag_id)
        db.execute(stmt)
        db.commit()
    
    db.close()
    
    return RedirectResponse("/admin", status_code=302)


@router.post("/photo/{photo_id}/tag/{tag_id}/delete")
async def remove_tag_from_photo(request: Request, photo_id: str, tag_id: str):
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import photo_tags
    
    db = SessionLocal()
    stmt = photo_tags.delete().where(
        (photo_tags.c.photo_id == photo_id) & (photo_tags.c.tag_id == tag_id)
    )
    db.execute(stmt)
    db.commit()
    db.close()
    
    return RedirectResponse("/admin", status_code=302)


@router.post("/photo/{photo_id}/rotate")
async def rotate_photo(request: Request, photo_id: str, direction: str = Form("cw")):
    """Rotate photo 90 degrees clockwise (cw) or counter-clockwise (ccw)"""
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import Photo
    from PIL import Image
    
    db = SessionLocal()
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    
    if not photo or not os.path.exists(photo.storage_path):
        db.close()
        return RedirectResponse("/admin", status_code=302)
    
    # Rotate the full image
    img = Image.open(photo.storage_path)
    
    if direction == "ccw":
        img = img.rotate(90, expand=True)
    else:
        img = img.rotate(-90, expand=True)
    
    img.save(photo.storage_path)
    
    # Regenerate thumbnail
    if photo.thumbnail_path and os.path.exists(photo.thumbnail_path):
        thumb = Image.open(photo.storage_path)
        thumb.thumbnail((300, 300), Image.LANCZOS)
        thumb.save(photo.thumbnail_path, "JPEG", quality=80)
    
    db.close()
    
    return RedirectResponse("/admin", status_code=302)


@router.get("/analytics")
async def analytics_page(request: Request):
    """Show analytics dashboard"""
    session = get_session(request)
    if session.get("role") != "admin":
        return RedirectResponse("/login?redirect=/admin/analytics", status_code=302)
    
    config = load_config()
    
    from app.database import SessionLocal
    from app.models import Photo, Tag, photo_tags
    from sqlalchemy import func
    
    db = SessionLocal()
    
    # Photo count
    photo_count = db.query(Photo).count()
    
    # Tag count
    tag_count = db.query(Tag).count()
    
    # Photos with tags
    photos_with_tags = db.query(photo_tags).distinct(photo_tags.c.photo_id).count()
    
    # Storage used
    total_size = 0
    for photo in db.query(Photo).all():
        if os.path.exists(photo.storage_path):
            total_size += os.path.getsize(photo.storage_path)
    
    # Recent uploads (last 24 hours)
    from datetime import datetime, timedelta
    recent_count = db.query(Photo).filter(
        Photo.upload_timestamp >= datetime.now() - timedelta(hours=24)
    ).count()
    
    db.close()
    
    # Format size
    if total_size > 1024 * 1024 * 1024:
        storage_gb = total_size / (1024 * 1024 * 1024)
        storage_str = f"{storage_gb:.2f} GB"
    else:
        storage_mb = total_size / (1024 * 1024)
        storage_str = f"{storage_mb:.2f} MB"
    
    return templates.TemplateResponse("analytics.html", {
        "request": {},
        "current_path": "/admin/analytics",
        "app_title": config.get("app_title", "PartyPix"),
        "photo_count": photo_count,
        "tag_count": tag_count,
        "photos_with_tags": photos_with_tags,
        "storage_used": storage_str,
        "recent_uploads": recent_count
    })


import os
from fastapi import templating
templates = templating.Jinja2Templates(directory="templates")
