import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routers.demo import router as demo_router
from backend.app.routers.oauth import router as oauth_router
from backend.app.routers.records import router as records_router
from backend.app.routers.stubs import router as stubs_router

VERSION = os.getenv("APP_VERSION", "0.1.0")

app = FastAPI(title="Anchorpoint", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict:
    return {"status": "ok", "version": VERSION}


app.include_router(api)
app.include_router(oauth_router)
app.include_router(records_router)
app.include_router(demo_router)
app.include_router(stubs_router)
