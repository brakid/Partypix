import json
from typing import Optional

import bcrypt
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse


def load_config():
    with open("config.json") as f:
        return json.load(f)


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_session_role(request: Request) -> Optional[str]:
    return request.session.get("role") if hasattr(request, "session") else None


async def require_guest(request: Request):
    role = request.session.get("role") if hasattr(request, "session") else None
    if role != "guest":
        return RedirectResponse("/login?redirect=" + request.url.path, status_code=302)
    return None


async def require_admin(request: Request):
    role = request.session.get("role") if hasattr(request, "session") else None
    if role != "admin":
        return RedirectResponse("/login?redirect=" + request.url.path, status_code=302)
    return None


class SessionMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        scope["state"] = {}
        session = {}
        cookie_header = scope.get("headers", [])
        
        for header in cookie_header:
            if header[0] == b"cookie":
                cookies = header[1].decode().split("; ")
                for cookie in cookies:
                    if cookie.startswith("session="):
                        session_data = cookie[8:]
                        try:
                            import base64
                            import json
                            decoded = base64.b64decode(session_data).decode()
                            session = json.loads(decoded)
                        except:
                            pass
        
        request.state.session = session
        request.state.config = load_config()
        
        async def send_wrapper(message):
            await send(message)
        
        await self.app(scope, receive, send_wrapper)
