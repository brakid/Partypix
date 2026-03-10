# Project Prompt Log

This document traces the conversation and requirements that led to the development of PartyPix.

## Initial Request

**User:** "brainstorm with me how to build a platform to let guests at a party upload their own pictures (from their phones) and have a shared access mechanism after the party. Ask me questions to clarify the requirements"

### Clarifying Questions Asked

1. **Access & Upload**
   - How should guests access the upload page? (QR code scan, unique link, no login required?)
   - Should guests be able to see *other guests'* uploads in real-time during the party, or only after?

2. **Post-Party Access**
   - Should all guests have equal access to all photos after the party, or should guests only see photos *they* uploaded?
   - How long should the photos be accessible?

3. **Storage & Technical**
   - What's your preferred tech approach? (Web app/PWA, native app, or no preference?)
   - Do you have a budget for cloud storage, or should it be cost-optimized/free?

4. **Features**
   - Should guests be able to like/react to photos?
   - Is there a need for photo moderation (host can delete)?

5. **Host**
   - Should the host be able to download all photos as a zip?

---

## User Responses

- **Access:** QR code or shared login credentials sufficient
- **Shared pool:** Yes, all guests see all photos
- **After-party:** Website access with tags (manual or AI-generated)
- **Tech:** Web app/PWA
- **Hosting:** Local solution (Raspberry Pi or similar)
- **No reactions needed**
- **Admin role needed:** Can delete images
- **Download:** Guests can select photos before downloading

---

## Second Round of Questions

1. **Network Access:** Will guests access the app over local WiFi at the party venue, or do you need it accessible from anywhere?
2. **Storage:** How many photos expected per party? Do you have external USB storage?
3. **AI Tagging:** Local Ollama (Pi) or cloud API?
4. **Download:** Zip file or individual selection?
5. **Timeline:** When's the party?

---

## User Responses (Round 2)

- **Network:** Local WiFi at party, ngrok for post-party
- **Storage:** ~20GB photos, external USB attached to Pi
- **AI Tagging:** Run externally (not on-the-fly) by admin after party before sharing. Tags should only be created by admin (not guests)
- **Download:** ZIP
- **Timeline:** Not specified

---

## Third Round of Questions

1. **Auth:** Should upload be open or require shared password?
2. **Multiple admins?**
3. **Language/framework preference?**
4. **Multiple parties or single instance?**
5. **AI Tagging approach:** Ollama script or cloud API?

---

## User Responses (Round 3)

- **Auth:** Shared guest password
- **Admin:** One admin account
- **Framework:** Python/FastAPI
- **Multi-party:** No single instance - expect to clone setup for repeated parties
- **AI Tagging:** Local Ollama script (semantic object detection - cake, presents, dancing, music, etc.)
- **AI Model:** qwen2.5vl:7b (chosen for M3 Mac with 24GB RAM)

---

## Design Decisions Confirmed

- **Thumbs:** Yes, for fast browsing experience
- **Deduplication:** No
- **Author on upload:** No
- **File size cap:** No cap
- **Clean install per party:** Yes, easy initialization

---

## Implementation Decisions Made

1. **Simplified Schema:** Removed `parties` table since single-party at a time
2. **Config storage:** JSON file for passwords and app title
3. **AI tagging:** Standalone script (Option A), not integrated into admin UI
4. **AI Model:** Default to qwen2.5vl:7b for M3 Mac compatibility (supports --model flag)

---

## Issues Encountered & Fixes

### 1. Template Error: `request.query_params`
**Problem:** Templates received dict, not FastAPI Request object  
**Fix:** Passed `redirect`, `current_path` as template variables instead of using `request.query_params`

### 2. Storage Directory Not Served
**Problem:** 404 on `/storage/thumbnails/`  
**Fix:** Added `app.mount("/storage", StaticFiles(directory="storage"))` to main.py

### 3. Multi-Photo Upload Not Working
**Problem:** `error=no_files` - files not reaching backend  
**Fix:** Changed input name from `file` to `files` to match backend parameter

### 4. DELETE Method Not Supported in HTML Forms
**Problem:** 405 Method Not Allowed when trying to delete tags  
**Fix:** Changed DELETE endpoint to POST at `/admin/photo/{photo_id}/tag/{tag_id}/delete`

### 5. Performance with Thousands of Images
**Question:** How will the system perform with several thousand images?  
**Discussion:** Brainstormed three approaches:
- Infinite scroll: Modern but memory issues, hard to share URLs
- Load More button: Good compromise but added complexity  
- Pagination: Chosen for simplicity and performance

**Decision:** Implement pagination (50 per page) - better memory management, URL sharing works, mobile-friendly

### 6. New Feature Requests from Customer Review
**Asked:** What other wishes might customers have?

**Brainstormed:**
- Single photo download
- QR code generator
- Analytics (photo count)
- Photo rotation
- Sort options (age, filename)
- Dark mode

**Implemented:**
- Single download: `/api/photos/{id}/download` endpoint
- QR code: `/qr` route with configurable URL
- Analytics: `/admin/analytics` with photo count, tags, storage
- Rotation: `/admin/photo/{id}/rotate` POST endpoint
- Sort: `?sort=newest|oldest|alpha` query param
- Dark mode: CSS custom properties + localStorage toggle

### 7. Tag Filter Toggle Behavior
**Issue:** Clicking on selected tag didn't return to "All" view
**Fix:** Updated template so selected tag link toggles back to `/gallery?sort=...` (no tag filter)

---

## Files Created

1. `requirements.txt` - Python dependencies
2. `init.py` - Database initialization script
3. `main.py` - FastAPI entry point
4. `app/database.py` - SQLAlchemy setup
5. `app/models.py` - Photo, Tag, PhotoTag models
6. `app/auth.py` - Password verification
7. `app/routes/upload.py` - Upload + login endpoints
8. `app/routes/gallery.py` - Gallery browsing
9. `app/routes/admin.py` - Admin CRUD
10. `app/routes/download.py` - ZIP download
11. `static/style.css` - Styling
12. `static/app.js` - Client interactions
13. `static/manifest.json` - PWA manifest
14. `templates/base.html` - Base layout
15. `templates/login.html` - Password entry
16. `templates/upload.html` - Upload page
17. `templates/gallery.html` - Photo gallery
18. `templates/admin.html` - Admin panel
19. `templates/qr.html` - QR code generator
20. `templates/analytics.html` - Analytics dashboard
21. `scripts/tag_photos.py` - Ollama tagging
20. `README.md` - Usage documentation
21. `DESIGN.md` - Architecture & design decisions
22. `.gitignore` - Git ignore patterns
