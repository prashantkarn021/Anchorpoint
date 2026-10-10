import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
