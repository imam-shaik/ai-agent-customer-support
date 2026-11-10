"""Versioned API router aggregation."""

from fastapi import APIRouter

from app.api.v1 import auth, chat, documents, feedback, provider_settings, retrieval, tickets

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(tickets.router)
api_router.include_router(feedback.router)
api_router.include_router(documents.router)
api_router.include_router(retrieval.router)
api_router.include_router(provider_settings.router)
