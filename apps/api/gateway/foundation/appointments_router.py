"""Lightweight Foundation appointment APIs; no AI reasoning."""

import os
from fastapi import APIRouter, HTTPException, Query

from apps.api.foundation.appointments.service import AppointmentService, AppointmentServiceError, MockHISClient

router = APIRouter(prefix="/v1/foundation", tags=["foundation-appointments"])

def service():
    return AppointmentService(MockHISClient(os.environ.get("MOCK_HIS_BASE_URL", "http://127.0.0.1:8001")))

def failure(exc):
    raise HTTPException(503, "appointment foundation data is unavailable") from exc

@router.get("/specialties")
def specialties():
    try:
        return service().list_specialties(page=1, page_size=100, is_active=True).to_dict()
    except AppointmentServiceError as exc: failure(exc)

@router.get("/doctors")
def doctors(specialty_id: str = Query(min_length=1)):
    try:
        return service().list_doctors(page=1, page_size=100, specialty_id=specialty_id, is_active=True).to_dict()
    except AppointmentServiceError as exc: failure(exc)

@router.get("/doctors/{doctor_id}/available-slots")
def slots(doctor_id: str):
    try:
        return service().list_available_slots(doctor_id=doctor_id, page=1, page_size=100).to_dict()
    except AppointmentServiceError as exc: failure(exc)
