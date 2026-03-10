#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
import uuid

import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def init_database(db_path: str, title: str, guest_password: str, admin_password: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    engine = create_engine(f"sqlite:///{db_path}")
    
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS photos (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                storage_path TEXT NOT NULL,
                thumbnail_path TEXT
            )
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tags (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL UNIQUE
            )
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS photo_tags (
                photo_id TEXT REFERENCES photos(id) ON DELETE CASCADE,
                tag_id TEXT REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (photo_id, tag_id)
            )
        """))
        
        conn.commit()
    
    config = {
        "guest_password_hash": hash_password(guest_password),
        "admin_password_hash": hash_password(admin_password),
        "app_title": title,
        "uploads_enabled": True,
    }
    
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    os.makedirs("storage/photos", exist_ok=True)
    os.makedirs("storage/thumbnails", exist_ok=True)
    
    print(f"✓ Database initialized: {db_path}")
    print(f"✓ Config saved: config.json")
    print(f"✓ Storage folders created")
    print(f"✓ App title: {title}")
    print(f"\nRun with: python main.py")


def main():
    parser = argparse.ArgumentParser(description="Initialize PartyPix database")
    parser.add_argument("--title", required=True, help="Party title")
    parser.add_argument("--guest-password", required=True, help="Guest access password")
    parser.add_argument("--admin-password", required=True, help="Admin password")
    
    args = parser.parse_args()
    
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    db_path = os.path.join(project_root, "app.db")
    init_database(db_path, args.title, args.guest_password, args.admin_password)


if __name__ == "__main__":
    main()
