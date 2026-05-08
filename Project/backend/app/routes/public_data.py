from __future__ import annotations

from fastapi import APIRouter

from app.services.public_data_collector import collect_public_data_once, get_public_data_status
from app.utils.response import ok


router = APIRouter()


@router.get("/api/public-data/status")
def public_data_status() -> dict:
    return ok(get_public_data_status())


@router.post("/api/public-data/refresh")
def refresh_public_data() -> dict:
    return ok(collect_public_data_once())
