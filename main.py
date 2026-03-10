#!/usr/bin/env python3
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse


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
templates = Jinja2Templates(directory="templates")

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
