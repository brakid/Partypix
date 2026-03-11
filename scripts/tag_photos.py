#!/usr/bin/env python3
"""
AI Tagging Script for PartyPix

Run this script after the party to automatically tag photos using Ollama.
Requires Ollama with a vision model installed.

Usage:
    python scripts/tag_photos.py                    # Tag + merge (default)
    python scripts/tag_photos.py --no-merge          # Tag only, skip merging
    python scripts/tag_photos.py --merge-only        # Only merge, skip tagging
    python scripts/tag_photos.py --model llama3.2-vision:11b  # Custom model

Supported models (Ollama):
    - qwen2.5vl:7b       (default, best for M3 Mac)
    - llama3.2-vision:11b
    - moondream:latest    (lightweight)
"""

import os
import sys
import uuid
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Photo, Tag, photo_tags

DEFAULT_MODEL = "qwen2.5vl:7b"

# Rule-based tag consolidations: tag_to_merge -> canonical_tag
TAG_CONSOLIDATIONS = {
    # Singular → Plural
    "child": "children",
    "kid": "children", 
    "kids": "children",
    "man": "people",
    "woman": "people",
    "person": "people",
    "friend": "people",
    "friends": "people",
    "guest": "people",
    "guests": "people",
    
    # Specific → General
    "dining table": "table",
    "dinner table": "table",
    "coffee table": "table",
    "desk": "table",
    
    # Celebration synonyms
    "celebration": "party",
    "festivity": "party",
    "festivities": "party",
    
    # Photo synonyms
    "photograph": "photo",
    "image": "photo",
    "picture": "photo",
    "selfie": "portrait",
    "portrait photo": "portrait",
    
    # Food
    "food": "food",
    "meal": "food",
    "dish": "food",
    "dishes": "food",
    
    # Drink
    "drink": "drinks",
    "beverage": "drinks",
    "beverages": "drinks",
    
    # Decoration
    "decorations": "decorations",
    "decoration": "decorations",
    "decor": "decorations",
    
    # Smile/Faces
    "smile": "smiling",
    "smiling": "smiling",
    "laugh": "laughing",
    "laughing": "laughing",
    "grin": "smiling",
    
    # Indoor/Outdoor
    "indoor": "indoors",
    "outdoor": "outdoors",
    "outside": "outdoors",
    
    # Night/Day
    "night": "nighttime",
    "day": "daytime",
}


def consolidate_tags(model: str = DEFAULT_MODEL, skip_llm: bool = False):
    """Consolidate similar tags using rule-based mappings and optional LLM."""
    print("=" * 50)
    print("TAG CONSOLIDATION")
    print("=" * 50)
    
    db = SessionLocal()
    
    try:
        # Get all tags
        all_tags = db.query(Tag).all()
        tag_labels = [t.label for t in all_tags]
        
        if not tag_labels:
            print("No tags to consolidate.")
            return
        
        print(f"Found {len(tag_labels)} unique tags: {', '.join(tag_labels)}")
        print()
        
        # Track merges to perform: {old_tag_label: new_tag_label}
        merges = {}
        
        # Step 1: Rule-based consolidation
        print("Step 1: Applying rule-based consolidations...")
        
        for tag in all_tags:
            tag_lower = tag.label.lower()
            if tag_lower in TAG_CONSOLIDATIONS:
                canonical = TAG_CONSOLIDATIONS[tag_lower]
                # Find or create canonical tag
                canonical_tag = db.query(Tag).filter(Tag.label == canonical).first()
                if not canonical_tag:
                    canonical_tag = Tag(id=str(uuid.uuid4()), label=canonical)
                    db.add(canonical_tag)
                    db.flush()
                
                if tag.id != canonical_tag.id:
                    merges[tag.label] = canonical_tag.label
                    print(f"  Rule: '{tag.label}' → '{canonical_tag.label}'")
        
        # Step 2: LLM-based consolidation (if enabled)
        if not skip_llm:
            print()
            print("Step 2: Running LLM consolidation...")
            
            try:
                import ollama
                
                prompt = f"""Given these tags from a party photo collection: {json.dumps(tag_labels)}
Identify tags that are semantically similar or redundant.
Return a JSON object where keys are tags to replace and values are the canonical tag to merge into.
Examples: {{"selfie": "portrait", "photograph": "photo", "celebration": "party"}}
Only return valid JSON, nothing else."""
                
                response = ollama.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                content = response.message.content.strip()
                # Extract JSON from response
                if "{" in content:
                    json_start = content.find("{")
                    json_end = content.rfind("}") + 1
                    json_str = content[json_start:json_end]
                    llm_merges = json.loads(json_str)
                    
                    for old, new in llm_merges.items():
                        if old in tag_labels and new in tag_labels:
                            if old not in merges or merges[old] != new:
                                # Verify target exists
                                if db.query(Tag).filter(Tag.label == new).first():
                                    merges[old] = new
                                    print(f"  LLM: '{old}' → '{new}'")
                
            except Exception as e:
                print(f"  LLM consolidation skipped: {e}")
        else:
            print("  (Skipped - using --no-merge flag)")
        
        if not merges:
            print()
            print("No consolidations needed.")
            return
        
        print()
        print(f"Applying {len(merges)} consolidations...")
        
        # Apply all changes - session is already in a transaction from query above
        for old_label, new_label in merges.items():
            old_tag = db.query(Tag).filter(Tag.label == old_label).first()
            new_tag = db.query(Tag).filter(Tag.label == new_label).first()
            
            if old_tag and new_tag:
                # Get all photo_ids that have the old tag
                old_entries = db.execute(
                    photo_tags.select().where(photo_tags.c.tag_id == old_tag.id)
                ).fetchall()
                
                merged_count = 0
                skipped_count = 0
                
                for entry in old_entries:
                    photo_id = entry.photo_id
                    # Check if this photo already has the new tag
                    existing = db.execute(
                        photo_tags.select().where(
                            photo_tags.c.photo_id == photo_id,
                            photo_tags.c.tag_id == new_tag.id
                        )
                    ).fetchone()
                    
                    if existing:
                        # Photo already has target tag - just remove old tag
                        db.execute(
                            photo_tags.delete().where(
                                photo_tags.c.photo_id == photo_id,
                                photo_tags.c.tag_id == old_tag.id
                            )
                        )
                        skipped_count += 1
                    else:
                        # Update to new tag
                        db.execute(
                            photo_tags.update()
                            .where(photo_tags.c.photo_id == photo_id)
                            .where(photo_tags.c.tag_id == old_tag.id)
                            .values(tag_id=new_tag.id)
                        )
                        merged_count += 1
                
                print(f"  Merged '{old_label}' → '{new_label}' ({merged_count} photos, {skipped_count} already had target)")
                
                db.delete(old_tag)
        
        db.commit()
        
        print()
        print("Consolidation complete!")
        
    finally:
        db.close()


def tag_photos(model: str = DEFAULT_MODEL, merge: bool = True):
    print("=" * 50)
    print("AI TAGGING")
    print("=" * 50)
    print(f"Using model: {model}")
    print(f"Make sure Ollama is running: ollama serve")
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
                    model=model,
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
    
    # Run consolidation after tagging
    if merge:
        consolidate_tags(model=model)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Tagging Script for PartyPix")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama vision model (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-merge", action="store_true", help="Skip tag consolidation after tagging")
    parser.add_argument("--merge-only", action="store_true", help="Only run tag consolidation, skip tagging")
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    if not os.path.exists("app.db"):
        print("ERROR: Database not found. Run init.py first.")
        sys.exit(1)
    
    if args.merge_only:
        consolidate_tags(model=args.model, skip_llm=False)
    else:
        tag_photos(model=args.model, merge=not args.no_merge)
