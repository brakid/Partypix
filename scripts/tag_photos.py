#!/usr/bin/env python3
"""
AI Tagging Script for PartyPix

Run this script after the party to automatically tag photos using Ollama.
Requires Ollama with a vision model (e.g., llama3.2-vision) installed.

Usage:
    python scripts/tag_photos.py
"""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Photo, Tag, photo_tags


def tag_photos():
    print("Starting AI tagging process...")
    print("Make sure Ollama is running with a vision model (e.g., llama3.2-vision)")
    print()
    
    try:
        import ollama
    except ImportError:
        print("ERROR: ollama package not installed.")
        print("Install with: pip install ollama")
        sys.exit(1)
    
    db = SessionLocal()
    
    try:
        photos = db.query(Photo).all()
        print(f"Found {len(photos)} photos to process")
        
        for i, photo in enumerate(photos, 1):
            existing_tags = db.query(Tag).join(photo_tags).filter(
                photo_tags.c.photo_id == photo.id
            ).all()
            
            if existing_tags:
                print(f"[{i}/{len(photos)}] Skipping {photo.original_filename} (already has tags)")
                continue
            
            print(f"[{i}/{len(photos)}] Processing {photo.original_filename}...")
            
            try:
                response = ollama.chat(
                    model='llama3.2-vision',
                    messages=[{
                        'role': 'user',
                        'content': '''Describe this image with 3-8 comma-separated keywords for objects, activities, and scenes. 
Examples: cake, dancing, confetti, group photo, decorations, balloons, music, friends, gifts.
Only respond with the keywords, nothing else.''',
                        'images': [photo.storage_path]
                    }]
                )
                
                content = response.message.content
                labels = [l.strip().lower() for l in content.split(',')]
                labels = [l for l in labels if l and len(l) < 30]
                labels = labels[:8]
                
                print(f"    Found tags: {', '.join(labels)}")
                
                for label in labels:
                    tag = db.query(Tag).filter(Tag.label == label).first()
                    
                    if not tag:
                        tag = Tag(id=str(uuid.uuid4()), label=label)
                        db.add(tag)
                        db.flush()
                    
                    stmt = photo_tags.insert().values(
                        photo_id=photo.id,
                        tag_id=tag.id
                    )
                    try:
                        db.execute(stmt)
                    except:
                        pass
                
                db.commit()
                print(f"    Added {len(labels)} tags")
                
            except Exception as e:
                print(f"    ERROR: {e}")
                continue
        
        print()
        print("Tagging complete!")
        
    finally:
        db.close()


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    if not os.path.exists("app.db"):
        print("ERROR: Database not found. Run init.py first.")
        sys.exit(1)
    
    tag_photos()
