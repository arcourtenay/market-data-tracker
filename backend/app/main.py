from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import ensure_schema
from .routers import companies, events, spac_events

settings = get_settings()

ensure_schema()

app = FastAPI(title="SEC Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(events.router)
app.include_router(spac_events.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
