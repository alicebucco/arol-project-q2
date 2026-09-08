"""Compose the public API routers."""

from fastapi import APIRouter

from api import auth, chat, commercial, machines, manuals, operations, system


router = APIRouter()
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(machines.router)
router.include_router(operations.router)
router.include_router(manuals.router)
router.include_router(commercial.router)
router.include_router(chat.router)
