# PartyPix

Photo sharing platform for parties. Guests upload photos from their phones to a shared pool, with post-party access via tunneled URL and AI-powered tagging.

## Features

- **QR code generator** - Generate scannable QR codes for guest access
- **Multi-photo upload** - select and upload multiple photos at once
- Drag and drop support for uploads
- Upload progress indicator
- Live shared photo pool during the party
- **Paginated gallery** - 50 photos per page for fast loading
- **Sort options** - Newest, oldest, or alphabetical
- Automatic thumbnail generation for fast browsing
- **Single photo download** - Download individual photos
- **Photo rotation** - Rotate photos 90° clockwise
- Admin panel for moderation (delete photos, add tags)
- **Analytics dashboard** - Photo count, tags, storage usage
- AI-powered semantic tagging using Ollama (post-party)
- Photo selection and ZIP download
- PWA support (add to home screen)

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Initialize for Your Party

```bash
python init.py \
    --title "Sarah's Birthday Bash" \
    --guest-password "party123" \
    --admin-password "secret123"
```

This creates:
- `app.db` - SQLite database
- `config.json` - Configuration with hashed passwords
- `storage/photos/` - Full-size images
- `storage/thumbnails/` - 300px thumbnails

### 3. Run During Party (Local Network)

```bash
python main.py --host 0.0.0.0 --port 8000
```

Guests access via `http://<pi-ip>:8000`. Display the QR code at the venue:
- Visit `/qr` to see the QR code
- Add `?url=<your-url>` to customize the URL (e.g., `/qr?url=http://192.168.1.100:8000`)

### 4. Post-Party Access (with ngrok)

```bash
ngrok http 8000 --authtoken <your-token>
```

Share the ngrok URL with guests for post-party browsing/download.

### 5. AI Tagging (Optional)

Requires [Ollama](https://ollama.ai/) installed with a vision model:

```bash
# Pull the vision model (qwen2.5vl:7b is default)
ollama pull qwen2.5vl:7b

# Start Ollama
ollama serve

# In another terminal, run the tagging script:
python scripts/tag_photos.py

# Or specify a different model:
python scripts/tag_photos.py --model llama3.2-vision:11b
```

This analyzes all photos and adds semantic tags like "cake", "dancing", "group photo", etc.

## Reset for New Party

For a fresh party, simply delete the files and reinitialize:

```bash
rm -rf app.db config.json storage/*
python init.py --title "New Party" --guest-password "pass" --admin-password "admin"
```

## File Structure

```
Partypix/
├── main.py              # FastAPI entry
├── init.py              # One-time setup
├── config.json          # Generated config
├── app.db               # SQLite database
├── app/
│   ├── database.py      # DB connection
│   ├── models.py        # Photo, Tag models
│   ├── auth.py          # Password auth
│   └── routes/         # API endpoints
├── static/              # CSS, JS
├── templates/           # HTML pages
├── storage/             # Photos + thumbnails
└── scripts/
    └── tag_photos.py    # AI tagging
```

## Requirements

- Python 3.10+
- Raspberry Pi (or any local server)
- USB storage for photos (recommended)
- ngrok (for post-party access)
- Ollama + vision model (for AI tagging)

## License

MIT
