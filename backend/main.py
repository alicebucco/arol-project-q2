"""FastAPI application entry point for the AROL Customer Platform backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat import chat
from api.routes import router
from api.schemas import ChatRequest, ChatResponse, QuoteLineChange


app = FastAPI(title="AROL Customer Platform API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # Vite may be opened through either localhost or 127.0.0.1 during local
    # development. Browsers treat them as distinct origins.
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Returned-Count", "X-Is-Truncated", "X-Limit"],
)
app.include_router(router)


__all__ = ["app", "ChatRequest", "ChatResponse", "QuoteLineChange", "chat"]
