#!/usr/bin/env python3
import os
import sys

# Use virtual environment if available
venv_python = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env", "bin", "python3")
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

"""
Face Detection Script for PartyPix

Run this script to detect faces in uploaded photos.
- First run: clusters all faces and assigns "Person 1", "Person 2", etc.
- Subsequent runs: detects new faces and matches to existing ones.

Usage:
    python scripts/detect_faces.py              # Detect new faces only
    python scripts/detect_faces.py --reprocess  # Re-process all photos
    python scripts/detect_faces.py --strict     # Use stricter threshold (0.4)
    python scripts/detect_faces.py --list       # List detected faces

Prerequisites:
    brew install cmake  # Required for dlib on Apple Silicon M3
    pip install -r requirements.txt
"""

import os
import sys
import uuid
import argparse
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.models import Photo, Face, PhotoFace, photo_faces
from PIL import Image


def get_face_thumbnail(image_path: str, bbox: tuple, size: tuple = (100, 100)) -> Image.Image:
    """Crop face from image and return as PIL Image."""
    img = Image.open(image_path)
    img = img.convert("RGB")
    
    top, right, bottom, left = bbox
    
    width = right - left
    height = bottom - top
    
    pad = int(max(width, height) * 0.2)
    
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(img.width, right + pad)
    bottom = min(img.height, bottom + pad)
    
    face_img = img.crop((left, top, right, bottom))
    face_img.thumbnail(size, Image.LANCZOS)
    
    return face_img


def save_face_thumbnail(face_img: Image.Image, face_id: str) -> str:
    """Save face thumbnail and return path."""
    thumbnail_dir = "storage/faces"
    os.makedirs(thumbnail_dir, exist_ok=True)
    
    thumbnail_path = f"{thumbnail_dir}/{face_id}.jpg"
    face_img.save(thumbnail_path, "JPEG", quality=80)
    
    return thumbnail_path


def detect_faces_in_image(image_path: str):
    """Detect faces in a single image. Returns list of (encoding, bbox)."""
    import face_recognition
    
    img = face_recognition.load_image_file(image_path)
    
    face_locations = face_recognition.face_locations(img, model="hog")
    face_encodings = face_recognition.face_encodings(img, face_locations)
    
    return list(zip(face_encodings, face_locations))


def cluster_faces(encodings: list, eps: float = 0.5, min_samples: int = 1):
    """Cluster face encodings using DBSCAN."""
    from sklearn.cluster import DBSCAN
    
    if not encodings:
        return [], []
    
    encodings_array = np.array(encodings)
    
    clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(encodings_array)
    
    labels = clustering.labels_
    
    unique_labels = set(labels)
    unique_labels.discard(-1)
    
    return labels, list(unique_labels)


def get_or_create_face(db, encoding: np.ndarray, threshold: float = 0.5) -> Face:
    """Match encoding to existing face or create new one."""
    existing_faces = db.query(Face).all()
    
    for face in existing_faces:
        if face.encoding is not None:
            encoding_arr = np.frombuffer(face.encoding)
            distance = np.linalg.norm(encoding_arr - encoding)
            
            if distance < threshold:
                return face
    
    new_face = Face(
        id=str(uuid.uuid4()),
        name=None,
        encoding=encoding.tobytes()
    )
    db.add(new_face)
    db.flush()
    
    return new_face


def detect_faces(reprocess: bool = False, threshold: float = 0.5):
    """Main detection function."""
    print("=" * 50)
    print("FACE DETECTION")
    print("=" * 50)
    
    init_db()
    
    db = SessionLocal()
    
    try:
        query = db.query(Photo)
        
        if not reprocess:
            already_processed = db.query(PhotoFace.photo_id).distinct()
            processed_ids = [row[0] for row in already_processed.all()]
            query = query.filter(~Photo.id.in_(processed_ids))
        
        photos = query.all()
        print(f"Found {len(photos)} photos to process")
        
        if not photos:
            print("No new photos to process.")
            return
        
        all_encodings = []
        photo_faces_data = []
        
        print()
        print("Detecting faces...")
        
        for i, photo in enumerate(photos, 1):
            storage_path = photo.storage_path
            
            if not os.path.exists(storage_path):
                print(f"  [{i}/{len(photos)}] Skipping {photo.original_filename} (file not found)")
                continue
            
            try:
                results = detect_faces_in_image(storage_path)
            except Exception as e:
                print(f"  [{i}/{len(photos)}] Error processing {photo.original_filename}: {e}")
                continue
            
            if not results:
                print(f"  [{i}/{len(photos)}] No faces in {photo.original_filename}")
                
                if reprocess:
                    db.execute(PhotoFace.__table__.delete().where(PhotoFace.photo_id == photo.id))
                
                continue
            
            print(f"  [{i}/{len(photos)}] Found {len(results)} face(s) in {photo.original_filename}")
            
            for encoding, bbox in results:
                all_encodings.append(encoding)
                photo_faces_data.append({
                    "photo_id": photo.id,
                    "encoding": encoding,
                    "bbox": bbox
                })
        
        if not photo_faces_data:
            print()
            print("No faces detected.")
            return
        
        print()
        print(f"Total faces detected: {len(photo_faces_data)}")
        
        existing_faces_count = db.query(Face).count()
        
        if existing_faces_count == 0:
            print()
            print("First run - clustering faces...")
            
            encodings = [pf["encoding"] for pf in photo_faces_data]
            labels, unique_labels = cluster_faces(encodings, eps=0.5)
            
            print(f"Found {len(unique_labels)} unique faces")
            
            face_map = {}
            
            for label in sorted(unique_labels):
                new_face = Face(
                    id=str(uuid.uuid4()),
                    name=None,
                    encoding=None
                )
                db.add(new_face)
                db.flush()
                face_map[label] = new_face
            
            for pf, label in zip(photo_faces_data, labels):
                if label == -1:
                    continue
                
                face = face_map[label]
                
                if face.encoding is None:
                    face.encoding = pf["encoding"].tobytes()
                
                top, right, bottom, left = pf["bbox"]
                
                # Check if this photo already has this face (dedupe)
                existing = db.execute(
                    photo_faces.select().where(
                        photo_faces.c.photo_id == pf["photo_id"],
                        photo_faces.c.face_id == face.id
                    )
                ).fetchone()
                
                if existing:
                    continue
                
                # Use raw insert instead of ORM
                db.execute(
                    photo_faces.insert().values(
                        photo_id=pf["photo_id"],
                        face_id=face.id,
                        bbox_x=left,
                        bbox_y=top,
                        bbox_w=right - left,
                        bbox_h=bottom - top
                    )
                )
            
            person_counter = 1
            for face in sorted(face_map.values(), key=lambda f: f.id):
                face.name = f"Person {person_counter}"
                person_counter += 1
            
            db.commit()
            
            print("Generating face thumbnails...")
            generate_face_thumbnails(db)
            
        else:
            print()
            print("Matching new faces to existing faces...")
            
            matched_count = 0
            new_face_count = 0
            
            for pf in photo_faces_data:
                face = get_or_create_face(db, pf["encoding"], threshold)
                
                if face.encoding is None:
                    face.encoding = pf["encoding"].tobytes()
                
                top, right, bottom, left = pf["bbox"]
                
                photo_face = PhotoFace(
                    photo_id=pf["photo_id"],
                    face_id=face.id,
                    bbox_x=left,
                    bbox_y=top,
                    bbox_w=right - left,
                    bbox_h=bottom - top
                )
                db.add(photo_face)
                
                matched_count += 1
            
            db.commit()
            
            print(f"Matched {matched_count} faces to existing or new faces")
            
            generate_face_thumbnails(db)
        
        print()
        print("Face detection complete!")
        
    finally:
        db.close()


def generate_face_thumbnails(db):
    """Generate thumbnail for each face from first photo containing it."""
    faces = db.query(Face).all()
    
    for face in faces:
        if os.path.exists(face.name + ".jpg") if face.name else False:
            continue
        
        pf = db.query(PhotoFace).filter(PhotoFace.face_id == face.id).first()
        
        if not pf:
            continue
        
        photo = db.query(Photo).filter(Photo.id == pf.photo_id).first()
        
        if not photo or not os.path.exists(photo.storage_path):
            continue
        
        bbox = (pf.bbox_y, pf.bbox_x + pf.bbox_w, pf.bbox_y + pf.bbox_h, pf.bbox_x)
        
        face_img = get_face_thumbnail(photo.storage_path, bbox)
        thumbnail_path = save_face_thumbnail(face_img, face.id)
        
        print(f"  Generated thumbnail for {face.name or face.id}")


def list_faces():
    """List all detected faces."""
    init_db()
    
    db = SessionLocal()
    
    try:
        faces = db.query(Face).all()
        
        if not faces:
            print("No faces detected yet.")
            return
        
        print("=" * 50)
        print("DETECTED FACES")
        print("=" * 50)
        
        for face in faces:
            count = db.query(PhotoFace).filter(PhotoFace.face_id == face.id).count()
            print(f"  {face.name or face.id}: {count} photo(s)")
        
        print()
        print(f"Total: {len(faces)} unique faces")
        
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Face detection for PartyPix")
    parser.add_argument("--reprocess", action="store_true", help="Re-process all photos")
    parser.add_argument("--strict", action="store_true", help="Use stricter threshold (0.4)")
    parser.add_argument("--threshold", type=float, default=0.5, help="Face match threshold")
    parser.add_argument("--list", action="store_true", help="List detected faces")
    
    args = parser.parse_args()
    
    if args.list:
        list_faces()
    elif args.strict:
        detect_faces(reprocess=args.reprocess, threshold=0.4)
    else:
        detect_faces(reprocess=args.reprocess, threshold=args.threshold)


if __name__ == "__main__":
    main()
