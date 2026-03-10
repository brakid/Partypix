#!/usr/bin/env python3
import os
import json
from contextlib import asynccontextmanager

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse


def create_templates():
    def range_func(start, stop):
        return range(start, stop)
    
    env = Jinja2Templates(directory="templates")
    env.env.globals['range'] = range_func
    return env


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists("config.json"):
        print("ERROR: Run init.py first to set up the database!")
        print("   python init.py --title 'My Party' --guest-password '1234' --admin-password 'admin'")
        sys.exit(1)
    
    with open("config.json") as f:
        app.state.config = json.load(f)
    
    yield


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")
templates = create_templates()

from app.routes import upload, gallery, admin, download

app.include_router(upload.router)
app.include_router(gallery.router)
app.include_router(admin.router)
app.include_router(download.router)


@app.get("/")
async def root():
    return RedirectResponse("/gallery")


@app.get("/login")
async def login_page(request: Request, redirect: str = "/gallery"):
    return templates.TemplateResponse("login.html", {
        "request": {}, 
        "redirect": redirect,
        "app_title": "PartyPix"
    })


@app.get("/qr")
async def qr_page(request: Request, url: Optional[str] = None, password: Optional[str] = None):
    """QR Code page showing URL for guests to access"""
    config = load_config()
    
    # Use provided URL or show placeholder for configuration
    qr_url = url or "http://YOUR-PI-ADDRESS:8000"
    qr_password = password or "[password]"
    
    # Generate QR code
    import qrcode
    import io
    import base64
    import qrcode
    from qrcode.image.pil import PilImage
    
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(qr_url)
    qr.make(fit=True)
    
    img: PilImage = qr.make_image(image_factory=PilImage)
    
    # Convert to base64 for embedding in HTML
    buffer = io.BytesIO()
    img.save(buffer)
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    qr_image = f"data:image/png;base64,{qr_base64}"
    
    return templates.TemplateResponse("qr.html", {
        "request": {},
        "current_path": "/qr",
        "app_title": config.get("app_title", "PartyPix"),
        "is_admin": False,
        "qr_image": qr_image,
        "url": qr_url,
        "password": qr_password
    })


def load_config():
    with open("config.json") as f:
        return json.load(f)


if __name__ == "__main__":
    import uvicorn
    import sys
    
    port = 8000
    host = "0.0.0.0"
    
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
        if arg == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]
    
    uvicorn.run(app, host=host, port=port)
