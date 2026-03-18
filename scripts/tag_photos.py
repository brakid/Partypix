#!/usr/bin/env python3
"""
AI Tagging Script for PartyPix

Run this script after the party to automatically tag photos using AI.
Requires a llama.cpp server running with a vision model.

Usage:
    python scripts/tag_photos.py                    # Tag + merge (default)
    python scripts/tag_photos.py --no-merge          # Tag only, skip merging
    python scripts/tag_photos.py --merge-only        # Only merge, skip tagging
    python scripts/tag_photos.py --retag             # Delete existing tags and re-tag

Requirements:
    - llama-server with vision model (e.g., Qwen3.5-9B) on port 8001
    - openai Python package (pip install openai)
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

DEFAULT_MODEL = "unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL"

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
    
    # Furniture
    "chair": "furniture",
    "chairs": "furniture",
    "couch": "furniture",
    "sofa": "furniture",
    "stool": "furniture",
    "stools": "furniture",
    
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
    
    # Nature
    "tree": "forest",
    "trees": "forest",
    "bush": "plants",
    "bushes": "plants",
    "flower": "flowers",
    
    # Items
    "backpack": "backpacks",
    "bag": "bags",
    "bags": "bags",
    "present": "presents",
    "gift": "presents",
    "gifts": "presents",
    
    # Clothing
    "hat": "hats",
    "cap": "hats",
    "shirt": "clothing",
    "dress": "clothing",
    "sunglasses": "accessories",
    
    # Places
    "house": "home",
    "houses": "home",
}


def get_llm_response(host: str, model: str, messages: list) -> str:
    """Call LLM via OpenAI-compatible API."""
    from openai import OpenAI
    
    if not host:
        host = "http://localhost:8001/v1"
    
    client = OpenAI(base_url=host, api_key="not-needed")
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    
    return response.choices[0].message.content


def get_vision_response(host: str, model: str, image_path: str, prompt: str) -> str:
    """Call vision model via OpenAI-compatible API with image."""
    from openai import OpenAI
    import base64
    
    if not host:
        host = "http://localhost:8001/v1"
    
    client = OpenAI(base_url=host, api_key="not-needed")
    
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
            ]
        }]
    )
    
    return response.choices[0].message.content


def extract_json(text: str) -> dict:
    """Extract JSON from LLM response with multiple fallback methods."""
    import re
    
    if not text:
        raise ValueError("Empty response")
    
    # Method 1: Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Method 2: Try to find JSON in markdown code block
    if "```json" in text:
        try:
            start = text.find("```json") + 7
            end = text.rfind("```")
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass
    elif "```" in text:
        try:
            start = text.find("```") + 3
            end = text.rfind("```")
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass
    
    # Method 3: Find first { and last } in the text
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        json_str = text[start:end]
        
        # Try to fix common JSON issues
        # Remove trailing commas
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    raise ValueError("Could not extract valid JSON from response")


def consolidate_tags(model: str, api_host: str, skip_llm: bool = False):
    """Consolidate similar tags using rule-based mappings and optional LLM."""
    print("=" * 50)
    print("TAG CONSOLIDATION")
    print("=" * 50)
    print(f"Using API host: {api_host}")
    
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
            
            prompt = f"""Given these tags from a party photo collection: {json.dumps(tag_labels)}
Identify ONLY very obvious duplicates that should be merged.
Be conservative - prefer keeping specific tags over merging to generic ones.

Rules:
- ONLY merge exact duplicates or very close synonyms
- Merge singular/plural (child->children, backpack->backpacks)
- Merge clear synonyms: gift->presents, selfie->portrait, photograph->photo, celebration->party
- DO NOT merge specific objects to generic categories (castle->structure, tree->forest are TOO GENERIC)
- When in doubt, DON'T merge - keeping specific tags is better

Examples of GOOD merges (keep these):
- {{"selfie": "portrait", "gift": "presents", "photograph": "photo"}}

Examples of BAD merges (too generic, DO NOT do):
- castle → structure (too generic, keep "castle")
- tree → forest (too generic, keep "tree")  
- car → vehicle (too generic, keep "car")
- building → architecture (too generic, keep "building")

Only return valid JSON with merges you are confident about. Empty {{}} is okay if no good merges found."""
            
            content = get_llm_response(
                host=api_host,
                model=model,
                messages=[{"role": "user", "content": prompt}],
            ).strip()
            
            try:
                llm_merges = extract_json(content)
                
                for old, new in llm_merges.items():
                    if old in tag_labels and new in tag_labels:
                        if old not in merges or merges[old] != new:
                            if db.query(Tag).filter(Tag.label == new).first():
                                merges[old] = new
                                print(f"  LLM: '{old}' → '{new}'")
                                
            except ValueError as e:
                print(f"  LLM response parsing failed: {e}")
                print(f"  Raw response (first 200 chars): {content[:200]}...")
            except Exception as e:
                print(f"  LLM consolidation error: {e}")
        else:
            print("  (Skipped - using --no-merge flag)")
        
        if not merges:
            print()
            print("No consolidations needed.")
            db.close()
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


def tag_photos(model: str = DEFAULT_MODEL, api_host: str = "http://localhost:8001", merge: bool = True, retag: bool = False):
    print("=" * 50)
    print("AI TAGGING")
    print("=" * 50)
    print(f"Using model: {model}")
    print(f"API host: {api_host or 'http://localhost:8001'}")
    if retag:
        print("Re-tagging ALL photos (deleting existing tags first)")
    print()
    
    db = SessionLocal()
    
    try:
        # Delete all existing tags if retag is True
        if retag:
            print("Deleting all existing tags...")
            db.execute(photo_tags.delete())
            db.query(Tag).delete()
            db.commit()
        
        photos = db.query(Photo).all()
        print(f"Found {len(photos)} photos to process")
        
        for i, photo in enumerate(photos, 1):
            existing_tags = db.query(Tag).join(photo_tags).filter(
                photo_tags.c.photo_id == photo.id
            ).all()
            
            if existing_tags and not retag:
                print(f"[{i}/{len(photos)}] Skipping {photo.original_filename} (already has tags)")
                continue
            
            print(f"[{i}/{len(photos)}] Processing {photo.original_filename}...")
            
            try:
                content = get_vision_response(
                    host=api_host,
                    model=model,
                    image_path=photo.storage_path,
                    prompt="Describe this image with 3-8 comma-separated keywords for objects, activities, and scenes. Examples: cake, dancing, confetti, group photo, decorations, balloons, music, friends, gifts. Only respond with the keywords, nothing else."
                )
                
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
        consolidate_tags(model=model, api_host=api_host)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Tagging Script for PartyPix")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--api-host", default="http://localhost:8001", help="llama.cpp server URL (default: http://localhost:8001)")
    parser.add_argument("--no-merge", action="store_true", help="Skip tag consolidation after tagging")
    parser.add_argument("--merge-only", action="store_true", help="Only run tag consolidation, skip tagging")
    parser.add_argument("--retag", action="store_true", help="Delete all existing tags and re-tag all photos from scratch")
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    if not os.path.exists("app.db"):
        print("ERROR: Database not found. Run init.py first.")
        sys.exit(1)
    
    # Extract args
    api_host = args.api_host

    if args.merge_only:
        consolidate_tags(model=args.model, api_host=api_host)
    else:
        tag_photos(model=args.model, api_host=api_host, merge=not args.no_merge, retag=args.retag)
