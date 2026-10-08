import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routers import admin, public
from app.scheduling import ensure_default_hours

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
settings = get_settings()
log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_default_hours(db)
    yield


app = FastAPI(
    title="Nord booking API",
    description=(
        "Online booking for a small barbershop. "
        "Log in with `POST /api/admin/login` first to try the admin endpoints here."
    ),
    lifespan=lifespan,
)

secret_key = settings.secret_key
if not secret_key:
    log.warning("SECRET_KEY is not set, using a random one. Admin sessions end on every restart.")
    secret_key = secrets.token_hex(32)

app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    session_cookie="nord_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=settings.cookie_secure,
)


@app.middleware("http")
async def add_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    path = request.url.path
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    # swagger pages load their own scripts, so they are left out of the policy
    if not path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    return response


app.include_router(public.router, prefix="/api")
app.include_router(admin.auth_router, prefix="/api/admin")
app.include_router(admin.router, prefix="/api/admin")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")
