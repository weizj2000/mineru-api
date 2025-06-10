from fastapi import APIRouter

from .task import router as file_extract_router

extract_router = APIRouter()
extract_router.include_router(file_extract_router, prefix="/api/v1")
