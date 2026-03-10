# PartyPix - Design Document

## Overview

PartyPix is a photo sharing platform designed for parties and events where guests can upload photos from their phones to a shared pool. The system operates locally during the party (on a Raspberry Pi or similar) and can be accessed remotely after the party via an ngrok tunnel.

## Problem Statement

At parties and events, guests take many photos but rarely share them with each other. Existing solutions require:
- Social media accounts
- Third-party services with privacy concerns
- Manual sharing of individual photos

PartyPix provides a simple, private solution where:
- Guests access via QR code and shared password
- All photos go to a shared pool instantly
- After the party, guests can browse and download photos
- AI tagging helps organize the photo collection

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Raspberry Pi (Host)                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        FastAPI Server                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │   │
│  │  │  Auth    │  │  Upload  │  │ Gallery  │  │ Admin Panel  │   │   │
│  │  │ Middleware│  │ Endpoint │  │ + thumbs │  │  (delete,    │   │   │
│  │  │          │  │          │  │          │  │   tag, dl)   │   │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │   │
│  │       │             │             │               │          │   │
│  │  ┌────┴─────────────┴─────────────┴───────────────┴────┐    │   │
│  │  │                   Business Logic                      │    │   │
│  │  └─────────────────────┬───────────────────────────────┘    │   │
│  │                        │                                    │   │
│  │  ┌─────────────────────┴───────────────────────────────┐    │   │
│  │  │              SQLite Database                        │    │   │
│  │  │   (photos, tags, photo_tags tables)                 │    │   │
│  │  └─────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────┐     ┌─────────────────────────────────────┐  │
│  │   USB Storage      │     │  ngrok tunnel (post-party only)    │  │
│  │  /photos/           │     │  → Cloud URL for guest access      │  │
│  │  /thumbnails/       │     └─────────────────────────────────────┘  │
│  └─────────────────────┘                                             │
└─────────────────────────────────────────────────────────────────────────┘

External: Ollama (local) → runs separately for AI tagging
```

### Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Backend | FastAPI (Python) | Lightweight, async, easy to deploy on Pi |
| Database | SQLite | Simple, file-based, no setup required, portable |
| Frontend | HTMX + Tailwind | No build step, progressive enhancement, fast |
| Auth | Cookie-based sessions | Simple, stateless, no external dependencies |
| Storage | Local filesystem | USB storage on Pi, cost-effective |
| Tagging | Ollama (local) | Privacy-first, no cloud costs, runs offline |

## Database Schema

### Photos Table

```sql
CREATE TABLE photos (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    storage_path TEXT NOT NULL,
    thumbnail_path TEXT
);
```

- `id`: UUID for unique identification
- `filename`: Internal UUID-based filename for storage
- `original_filename`: Original name for display/download
- `upload_timestamp`: For sorting by time
- `storage_path`: Path to full-resolution image
- `thumbnail_path`: Path to 300px thumbnail

### Tags Table

```sql
CREATE TABLE tags (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL UNIQUE
);
```

- `label`: Human-readable tag (e.g., "cake", "dancing")
- Unique constraint prevents duplicates

### Photo Tags Junction Table

```sql
CREATE TABLE photo_tags (
    photo_id TEXT REFERENCES photos(id) ON DELETE CASCADE,
    tag_id TEXT REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (photo_id, tag_id)
);
```

- Many-to-many relationship between photos and tags
- CASCADE delete ensures referential integrity

## Design Decisions

### 1. Single-Party Instance

**Decision:** The system is designed for a single party at a time, with a clean installation per party.

**Rationale:**
- Simplifies the codebase significantly
- No need for party management UI
- Reset for new party = delete files + re-init
- Each party gets fresh storage and database

**Trade-off:** Users must re-run init.py for each party. This is acceptable since parties are discrete events.

### 2. Shared Password for Guests

**Decision:** Single shared password for all guests, not individual accounts.

**Rationale:**
- Zero friction for guests - just one password to enter
- No registration process needed
- QR code can display the password
- Simpler auth implementation

**Trade-off:** No attribution of who uploaded which photo (unless added as future feature). Guests wanted no author field per requirements.

### 3. Cookie-Based Sessions

**Decision:** Simple base64-encoded JSON in HTTP-only cookies.

```python
session_data = json.dumps({"role": "guest"})
encoded = base64.b64encode(session_data.encode()).decode()
response.set_cookie("session", encoded, httponly=True, samesite="lax")
```

**Rationale:**
- No server-side session storage needed
- Stateless design
- Simple to implement
- Secure enough for party use (not banking-grade)

**Security Note:** Not cryptographically signed. Acceptable for party use where worst case is unauthorized photo access.

### 4. Thumbnail Generation on Upload

**Decision:** Generate thumbnails immediately when photo is uploaded.

```python
img = Image.open(storage_path)
img.thumbnail((300, 300), Image.LANCZOS)
img.save(thumbnail_path, "JPEG", quality=80)
```

**Rationale:**
- Faster gallery loading (thumbnails load instead of full images)
- Consistent 300px width maintains grid layout
- JPEG quality 80 balances size vs. quality

**Trade-off:** Upload takes slightly longer. Acceptable given small party scale.

### 5. Local Ollama for AI Tagging

**Decision:** AI tagging runs as a standalone script, not integrated into the web app.

**Rationale:**
- Ollama can be resource-intensive
- Only admin needs to run it (post-party)
- Simpler web app (fewer dependencies)
- Admin can run overnight without affecting guests

**Workflow:**
1. Party ends
2. Admin runs `python scripts/tag_photos.py`
3. Script processes all photos via Ollama vision model
4. Tags are saved to database
5. Guests can now filter by tags

### 6. ZIP Download for Selected Photos

**Decision:** Guests select photos and download as ZIP file.

```python
with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
    for photo in photos:
        zf.write(photo.storage_path, photo.original_filename)
```

**Rationale:**
- Single download for multiple photos
- Preserves original filenames
- Standard format, works on all devices

**Trade-off:** Large ZIP files may be slow to generate. Acceptable for party scale.

### 7. Template Engine Choice (Jinja2)

**Decision:** Use Jinja2 templates instead of API + React/Vue.

**Rationale:**
- Simpler deployment (no build step)
- Progressive enhancement works without JS
- HTMX handles interactivity
- Fast enough for party use

**Trade-off:** Less dynamic than SPA. Acceptable for read-mostly gallery.

### 8. UUID Filenames

**Decision:** Store photos with UUID filenames.

```python
photo_id = str(uuid.uuid4())
filename = f"{photo_id}.{ext}"
```

**Rationale:**
- No filename collisions
- No need to sanitize user input
- Simple internal organization

### 9. Multi-Photo Upload with Progress Tracking

**Decision:** Support uploading multiple photos simultaneously with sequential processing and visual progress feedback.

```javascript
// Client-side: sequential upload with progress
function uploadNext(index) {
    const formData = new FormData();
    formData.append('files', files[index]);
    
    fetch('/upload', { method: 'POST', body: formData })
        .then(() => {
            progressBar.style.width = (uploaded / files.length * 100) + '%';
            uploadNext(index + 1);
        });
}
```

```python
# Server-side: handle list of files
@router.post("/upload")
async def upload_photos(request: Request, files: Union[list[UploadFile], None] = None):
    for file in files:
        await save_photo(file)
```

**Rationale:**
- Guests typically want to upload multiple photos at once
- Sequential upload prevents server overload
- Progress indicator gives feedback during upload
- Drag & drop support for intuitive UX

**Trade-off:** 
- Slightly slower than parallel upload (mitigated by sequential approach)
- Requires JavaScript for best experience (fallback to single upload works)

### 10. Pagination vs Infinite Scroll

**Decision:** Use server-side pagination (50 photos per page) instead of infinite scroll.

```python
PHOTOS_PER_PAGE = 50

# Database query with pagination
photos = query.order_by(Photo.upload_timestamp.desc())\
    .offset((page - 1) * PHOTOS_PER_PAGE)\
    .limit(PHOTOS_PER_PAGE)\
    .all()
```

**Alternatives Considered:**

| Approach | Pros | Cons |
|----------|------|------|
| Infinite Scroll | Modern feel, seamless | Memory grows, mobile janky, hard to share |
| Load More Button | Good UX | Added complexity |
| **Pagination (chosen)** | Predictable, shareable URLs, memory-efficient | Requires clicking |

**Rationale:**
- **Memory efficiency**: With thousands of photos, infinite scroll causes browser memory issues
- **URL sharing**: After-party guests may share links - pagination URLs work better
- **Mobile performance**: Infinite scroll can be jittery on mobile browsers
- **Intent-based**: Party guests are looking for specific photos - pagination supports this better
- **Simplicity**: Less JavaScript complexity, more reliable

**Trade-off:** Requires clicking to see more, but acceptable for the use case

### 11. Dark Mode Implementation

**Decision:** Use CSS custom properties with media query for auto-detection and localStorage for manual toggle.

```css
/* CSS Custom Properties */
:root {
  --bg: #fafafa;
  --text: #1f2937;
}

/* Auto-detect system preference */
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111827;
    --text: #f9fafb;
  }
}

/* Manual toggle class */
body.dark {
  --bg: #111827;
  --text: #f9fafb;
}
```

**Rationale:**
- Zero JavaScript required for basic functionality
- Respects user privacy (no tracking)
- Smooth transition between modes
- Persists preference across sessions

### 12. QR Code Generation

**Decision:** Generate QR codes server-side using qrcode library and embed as base64.

```python
import qrcode
import io
import base64

qr = qrcode.QRCode(box_size=10, border=4)
qr.add_data(url)
img = qr.make_image()
buffer = io.BytesIO()
img.save(buffer)
qr_base64 = base64.b64encode(buffer.getvalue()).decode()
```

**Rationale:**
- No client-side dependencies
- Customizable URL parameter
- Works without JavaScript
- Simple to implement

### 13. Photo Rotation

**Decision:** Rotate 90° clockwise, regenerate thumbnail, save permanently.

```python
img = Image.open(photo.storage_path)
img = img.rotate(-90, expand=True)
img.save(photo.storage_path)

# Regenerate thumbnail
thumb = Image.open(photo.storage_path)
thumb.thumbnail((300, 300), Image.LANCZOS)
thumb.save(thumbnail_path, "JPEG", quality=80)
```

**Rationale:**
- Permanent rotation matches user intent
- Thumbnail stays consistent with full image
- Simple single-direction rotation (cw) is sufficient for most cases)

### 14. Mobile-First Responsive Design

**Decision:** Use mobile-first CSS with progressive enhancement for larger screens.

```css
/* Base: Mobile (2 columns) */
.gallery-grid {
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
}

/* Tablet */
@media (min-width: 640px) {
  .gallery-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .gallery-grid {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
}
```

**Mobile Improvements:**
- 2-column gallery on mobile (vs 4+ on desktop)
- Touch-friendly buttons (min 44px)
- Full-width buttons on mobile
- Responsive navigation
- Optimized form inputs (prevents iOS zoom)
- Full-width mobile-friendly layout

**Rationale:**
- Most guests access from phones
- Touch targets must be minimum 44px for accessibility
- Progressive enhancement: works on all devices, optimized on larger screens

## Features

### During Party (Local Network)

| Feature | Description |
|---------|-------------|
| QR Code Access | Guests scan QR to access upload page |
| Shared Password | Single password for all guests |
| **Multi-Photo Upload** | Select and upload multiple photos at once |
| Drag & Drop | Drag photos directly onto the upload page |
| Upload Progress | Visual indicator showing upload status |
| Live Uploads | Photos appear in gallery immediately |
| Thumbnail Grid | Fast-loading thumbnail gallery |
| **Paginated Gallery** | 50 photos per page for performance |
| **Sort Options** | Sort by newest, oldest, or alphabetical |
| **Dark Mode** | Auto-detects system preference |
| **Mobile-First Design** | Responsive layout optimized for phones |
| **Upload Toggle** | Enable/disable guest uploads |
| Admin Panel | Delete photos, manage tags |

### Post-Party (via ngrok)

| Feature | Description |
|---------|-------------|
| Remote Access | Access via ngrok tunnel URL |
| Tag Filtering | Filter photos by AI-generated tags |
| **Pagination** | Browse large collections efficiently |
| **Sort Options** | Sort by newest, oldest, or alphabetical |
| Photo Selection | Checkbox to select multiple photos |
| **Single Download** | Download individual photos |
| ZIP Download | Download selected photos as ZIP |
| Browse Gallery | Full-resolution photo viewing |
| **Dark Mode** | Manual toggle available |

### Admin Features

| Feature | Description |
|---------|-------------|
| Photo Deletion | Remove unwanted photos |
| **Photo Rotation** | Rotate photos 90° clockwise |
| Manual Tagging | Add/remove tags manually |
| Tag Management | Create new tags |
| **Analytics Dashboard** | Photo count, tags, storage usage |
| AI Tagging Script | Run Ollama to auto-tag |

## File Structure

```
Partypix/
├── main.py              # FastAPI entry point
├── init.py              # Database & config initialization
├── config.json          # Hashed passwords, app title
├── app.db               # SQLite database
├── requirements.txt     # Python dependencies
├── app/
│   ├── __init__.py
│   ├── database.py      # SQLAlchemy setup
│   ├── models.py        # Photo, Tag, PhotoTag models
│   ├── auth.py          # Password verification
│   └── routes/
│       ├── __init__.py
│       ├── upload.py    # Upload + login endpoints
│       ├── gallery.py   # Gallery browsing
│       ├── admin.py     # Admin CRUD operations
│       └── download.py  # ZIP download
├── static/
│   ├── style.css        # Tailwind-inspired CSS
│   ├── app.js           # Client-side interactions
│   └── manifest.json    # PWA manifest
├── templates/
│   ├── base.html        # Base layout
│   ├── login.html       # Password entry
│   ├── upload.html      # Upload page
│   ├── gallery.html     # Photo gallery
│   ├── admin.html       # Admin panel
│   ├── qr.html          # QR code generator
│   └── analytics.html   # Analytics dashboard
├── storage/
│   ├── photos/          # Full-size images
│   └── thumbnails/      # 300px thumbnails
└── scripts/
    └── tag_photos.py    # Ollama AI tagging
```

## Security Considerations

### Current Measures

1. **Password Hashing**: Uses bcrypt for password storage
2. **HTTP-Only Cookies**: Session cookies not accessible via JavaScript
3. **SameSite Policy**: Cookies restricted to same-origin
4. **File Type Validation**: Only images accepted for upload
5. **UUID Filenames**: No path traversal or filename injection

### Limitations

- No HTTPS by default (local network only)
- Session tokens not cryptographically signed
- No rate limiting on uploads
- No encryption at rest

These are acceptable for:
- Closed network (party WiFi)
- Non-sensitive content (party photos)
- Short-lived access (party duration + short after-period)

## Deployment

### Raspberry Pi Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize for party
python init.py --title "Birthday Bash" --guest-password "party123" --admin-password "secret"

# Run locally
python main.py --host 0.0.0.0 --port 8000
```

### Post-Party Access

```bash
# Install ngrok
brew install ngrok  # or download from ngrok.com

# Start tunnel
ngrok http 8000 --authtoken <your-token>

# Share the .ngrok.io URL with guests
```

### AI Tagging

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull vision model (qwen2.5vl:7b recommended for M3 Mac)
ollama pull qwen2.5vl:7b

# Run tagging
python scripts/tag_photos.py

# Or use a different model
python scripts/tag_photos.py --model llama3.2-vision:11b
```

## Future Enhancements

Potential features not currently implemented:

1. **Slideshow Mode**: Auto-advancing fullscreen photos
2. **Photo Comments**: Guests can add captions
3. **Slideshow Download**: Frame-by-frame video export
4. **Multiple Events**: Support multiple parties per installation
5. **Social Sharing**: Direct share to Instagram/Stories
6. **QR Generator**: Built-in QR code for URL/password

## Appendix: Dependencies

```
fastapi==0.115.0        # Web framework
uvicorn==0.32.0         # ASGI server
sqlalchemy==2.0.35      # ORM
python-multipart==0.0.12  # File uploads
pillow==11.0.0          # Image processing
python-jose[cryptography]==3.3.0  # JWT (unused but related)
passlib[bcrypt]==1.7.4  # Password hashing
aiofiles==24.1.0        # Async file I/O
jinja2==3.1.4           # Templates
```

## License

MIT
