import base64
import json
import os
from typing import Optional

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
async def gallery(request: Request, tag: str = None, face: str = None, page: int = 1, sort: str = "newest", error: str = None, success: str = None):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return RedirectResponse(f"/login?redirect=/gallery", status_code=302)
    
    config = load_config()
    
    from app.database import SessionLocal
    from app.models import Photo, Tag, Face, PhotoFace
    
    db = SessionLocal()
    
    base_query = db.query(Photo)
    if tag:
        base_query = base_query.join(Photo.tags).filter(Tag.label == tag)
    
    if face:
        base_query = base_query.join(PhotoFace).filter(PhotoFace.face_id == face)
    
    # Apply sorting
    if sort == "oldest":
        order = Photo.upload_timestamp.asc()
    elif sort == "alpha":
        order = Photo.original_filename.asc()
    else:  # newest (default)
        order = Photo.upload_timestamp.desc()
    
    total_photos = base_query.count()
    total_pages = (total_photos + PHOTOS_PER_PAGE - 1) // PHOTOS_PER_PAGE
    
    photos = base_query.order_by(order)\
        .offset((page - 1) * PHOTOS_PER_PAGE)\
        .limit(PHOTOS_PER_PAGE)\
        .all()
    
    tags = db.query(Tag).order_by(Tag.label).all()
    faces = db.query(Face).order_by(Face.name).all()
    
    import os
    faces_data = []
    for f in faces:
        thumbnail_path = f"/storage/faces/{f.id}.jpg" if os.path.exists(f"storage/faces/{f.id}.jpg") else None
        faces_data.append({
            "id": f.id,
            "name": f.name,
            "thumbnail": thumbnail_path
        })
    
    photo_list = []
    for p in photos:
        photo_faces = db.query(PhotoFace).filter(PhotoFace.photo_id == p.id).all()
        face_ids = [pf.face_id for pf in photo_faces]
        
        photo_list.append({
            "id": p.id,
            "thumbnail_path": "/" + p.thumbnail_path if p.thumbnail_path else None,
            "original_filename": p.original_filename,
            "upload_timestamp": p.upload_timestamp.isoformat() if p.upload_timestamp else None,
            "tags": [t.label for t in sorted(p.tags, key=lambda t: t.label)],
            "face_ids": face_ids
        })
    
    db.close()
    
    return templates.TemplateResponse("gallery.html", {
        "request": {},
        "current_path": "/gallery",
        "photos": photo_list,
        "tags": [{"label": t.label} for t in tags],
        "faces": faces_data,
        "selected_tag": tag,
        "selected_face": face,
        "current_page": page,
        "total_pages": total_pages,
        "total_photos": total_photos,
        "current_sort": sort,
        "app_title": config.get("app_title", "PartyPix"),
        "is_admin": session.get("role") == "admin",
        "error": error,
        "success": success
    })


@router.get("/api/photos")
async def api_photos(request: Request, tag: str = None, face: str = None, page: int = 1, sort: str = "newest"):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import Photo, Tag, PhotoFace
    
    db = SessionLocal()
    query = db.query(Photo)
    if tag:
        query = query.join(Photo.tags).filter(Tag.label == tag)
    
    if face:
        query = query.join(PhotoFace).filter(PhotoFace.face_id == face)
    
    # Apply sorting
    if sort == "oldest":
        order = Photo.upload_timestamp.asc()
    elif sort == "alpha":
        order = Photo.original_filename.asc()
    else:
        order = Photo.upload_timestamp.desc()
    
    total = query.count()
    photos = query.order_by(order)\
        .offset((page - 1) * PHOTOS_PER_PAGE)\
        .limit(PHOTOS_PER_PAGE)\
        .all()
    
    result = []
    for p in photos:
        photo_faces = db.query(PhotoFace).filter(PhotoFace.photo_id == p.id).all()
        
        result.append({
            "id": p.id,
            "thumbnail": "/" + p.thumbnail_path if p.thumbnail_path else None,
            "full": f"/api/photos/{p.id}/full",
            "download": f"/api/photos/{p.id}/download",
            "tags": [t.label for t in sorted(p.tags, key=lambda t: t.label)],
            "faces": [pf.face_id for pf in photo_faces]
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


@router.get("/api/faces")
async def api_faces(request: Request):
    session = get_session(request)
    if session.get("role") not in ["guest", "admin"]:
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import Face, PhotoFace
    
    db = SessionLocal()
    faces = db.query(Face).all()
    
    result = []
    for f in faces:
        count = db.query(PhotoFace).filter(PhotoFace.face_id == f.id).count()
        
        thumbnail_path = f"/storage/faces/{f.id}.jpg" if os.path.exists(f"storage/faces/{f.id}.jpg") else None
        
        result.append({
            "id": f.id,
            "name": f.name,
            "photo_count": count,
            "thumbnail": thumbnail_path
        })
    
    db.close()
    return {"faces": result}


@router.patch("/api/faces/{face_id}")
async def rename_face(request: Request, face_id: str):
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    import json
    body = await request.body()
    data = json.loads(body)
    new_name = data.get("name")
    
    from app.database import SessionLocal
    from app.models import Face
    
    db = SessionLocal()
    face = db.query(Face).filter(Face.id == face_id).first()
    
    if not face:
        db.close()
        return {"error": "not found"}
    
    face.name = new_name
    db.commit()
    db.close()
    
    return {"success": True, "id": face_id, "name": new_name}


@router.delete("/api/faces/{face_id}")
async def delete_face(request: Request, face_id: str):
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    from app.database import SessionLocal
    from app.models import Face, photo_faces
    
    db = SessionLocal()
    
    face = db.query(Face).filter(Face.id == face_id).first()
    if not face:
        db.close()
        return {"error": "not found"}
    
    # Delete all photo_faces entries for this face
    db.execute(photo_faces.delete().where(photo_faces.c.face_id == face_id))
    
    # Delete the face
    db.delete(face)
    db.commit()
    db.close()
    
    return {"success": True, "id": face_id}


@router.post("/api/faces/merge")
async def merge_faces(request: Request):
    session = get_session(request)
    if session.get("role") != "admin":
        return {"error": "unauthorized"}
    
    import json
    body = await request.body()
    data = json.loads(body)
    
    source_ids = data.get("source_ids", [])
    target_id = data.get("target_id")
    new_name = data.get("name")
    
    if not target_id:
        return {"error": "target_id required"}
    
    if not source_ids:
        return {"error": "source_ids required"}
    
    from app.database import SessionLocal
    from app.models import Face, photo_faces
    
    db = SessionLocal()
    
    target_face = db.query(Face).filter(Face.id == target_id).first()
    if not target_face:
        db.close()
        return {"error": "target not found"}
    
    for source_id in source_ids:
        if source_id == target_id:
            continue
        
        # Get all photo_faces entries for source
        source_entries = db.execute(
            photo_faces.select().where(photo_faces.c.face_id == source_id)
        ).fetchall()
        
        for entry in source_entries:
            # Check if target already exists in this photo
            existing = db.execute(
                photo_faces.select().where(
                    photo_faces.c.photo_id == entry.photo_id,
                    photo_faces.c.face_id == target_id
                )
            ).fetchone()
            
            if existing:
                # Delete source entry (target already present)
                db.execute(
                    photo_faces.delete().where(
                        photo_faces.c.photo_id == entry.photo_id,
                        photo_faces.c.face_id == source_id
                    )
                )
            else:
                # Update to target
                db.execute(
                    photo_faces.update()
                    .where(photo_faces.c.photo_id == entry.photo_id)
                    .where(photo_faces.c.face_id == source_id)
                    .values(face_id=target_id)
                )
        
        # Delete source face
        source_face = db.query(Face).filter(Face.id == source_id).first()
        if source_face:
            db.delete(source_face)
    
    # Rename target if provided
    if new_name:
        target_face.name = new_name
    
    db.commit()
    db.close()
    
    return {"success": True, "target_id": target_id}


def create_templates():
    def range_func(start, stop):
        return range(start, stop)
    
    env = templating.Jinja2Templates(directory="templates")
    env.env.globals['range'] = range_func
    return env

templates = create_templates()
