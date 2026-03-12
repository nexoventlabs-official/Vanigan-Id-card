from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pymongo import ASCENDING

from app.api.routes import admin, auth, public, whatsapp
from app.core.config import settings
from app.core.db import get_member_collection, get_whatsapp_session_collection

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(public.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(whatsapp.router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
async def startup_event():
    members = get_member_collection()
    sessions = get_whatsapp_session_collection()
    await members.create_index([("unique_id", ASCENDING)], unique=True)
    await members.create_index([("contact_number", ASCENDING)])
    await sessions.create_index([("wa_id", ASCENDING)], unique=True)


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    members = get_member_collection()
    await members.count_documents({})
    return {"status": "ok"}


@app.get("/verify/{unique_id}")
async def verify_redirect(unique_id: str):
    return RedirectResponse(url=f"{settings.api_v1_prefix}/public/verify-card/{unique_id}")
