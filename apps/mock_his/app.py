# === TASK:WP-104:START ===
"""Mock HIS FastAPI application for Hospital Assistant.

This module provides a mock Hospital Information System (HIS) API that
simulates the behavior of a real HIS for development and testing purposes.
It loads seed data from JSON files and provides REST endpoints for
specialties, doctors, slots, and appointments.

The mock HIS follows the data contracts defined in:
- docs/artifacts/interface/foundation-api-contracts.md (INT-03)
- docs/artifacts/interface/data-contracts.md (INT-04)
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mock HIS",
    description="Mock Hospital Information System for development and testing",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Data models (Pydantic for request/response validation)
# ---------------------------------------------------------------------------


class SpecialtyResponse(BaseModel):
    specialty_id: str
    code: str
    name: str
    department_id: str
    description: str = ""
    is_active: bool = True


class DoctorResponse(BaseModel):
    doctor_id: str
    full_name: str
    title: str = ""
    specialty_ids: List[str] = Field(default_factory=list)
    department_id: str
    facility: str = ""
    profile_summary: str = ""
    is_active: bool = True


class SlotResponse(BaseModel):
    slot_id: str
    doctor_id: str
    date: str
    time: str
    room: str
    status: str


class AppointmentCreateRequest(BaseModel):
    doctor_id: str
    slot_id: str
    patient_name: str
    patient_phone: str
    patient_dob: str
    has_insurance: bool
    visit_reason: str
    visit_type: str
    confirmation_token: str
    idempotency_key: Optional[str] = None


class AppointmentResponse(BaseModel):
    appointment_id: str
    doctor_id: str
    slot_id: str
    patient_name: str
    patient_phone: str
    patient_dob: str
    has_insurance: bool
    visit_reason: str
    visit_type: str
    status: str
    rejection_reason: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# In-memory data store with thread-safe access
# ---------------------------------------------------------------------------


@dataclass
class MockHISDataStore:
    """Thread-safe in-memory data store for mock HIS data."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _specialties: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _doctors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _slots: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _appointments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _idempotency_cache: Dict[str, str] = field(default_factory=dict)  # key -> appointment_id
    _appointment_counter: int = 0
    _loaded: bool = False
    _default_status: str = "pending"

    def load_from_file(self, file_path: Path) -> None:
        """Load data from JSON seed file."""
        with self._lock:
            if self._loaded:
                return

            if not file_path.exists():
                # Initialize with empty data if file not found
                self._loaded = True
                return

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load dataset metadata
            dataset = data.get("dataset", {})
            self._default_status = dataset.get("default_appointment_status", "pending")

            # Load specialties
            for specialty in data.get("specialties", []):
                self._specialties[specialty["specialty_id"]] = specialty

            # Load doctors
            for doctor in data.get("doctors", []):
                self._doctors[doctor["doctor_id"]] = doctor

            # Load slots
            for slot in data.get("slots", []):
                self._slots[slot["slot_id"]] = slot

            # Load existing appointments
            for appointment in data.get("appointments", []):
                self._appointments[appointment["appointment_id"]] = appointment
                # Parse counter from existing appointment IDs
                aid = appointment["appointment_id"]
                match = re.search(r"HEN-\d{4}-(\d{4})", aid)
                if match:
                    num = int(match.group(1))
                    if num > self._appointment_counter:
                        self._appointment_counter = num

            self._loaded = True

    def _generate_appointment_id(self) -> str:
        """Generate a new appointment ID."""
        self._appointment_counter += 1
        year = datetime.now(dt_timezone.utc).year
        return f"HEN-{year}-{self._appointment_counter:04d}"

    def list_specialties(self) -> List[Dict[str, Any]]:
        """Return all specialties."""
        with self._lock:
            return list(self._specialties.values())

    def list_doctors(self) -> List[Dict[str, Any]]:
        """Return all doctors."""
        with self._lock:
            return list(self._doctors.values())

    def list_slots(self) -> List[Dict[str, Any]]:
        """Return all slots."""
        with self._lock:
            return list(self._slots.values())

    def get_slot(self, slot_id: str) -> Optional[Dict[str, Any]]:
        """Get a slot by ID."""
        with self._lock:
            return self._slots.get(slot_id)

    def update_slot_status(self, slot_id: str, status: str) -> bool:
        """Update slot status."""
        with self._lock:
            if slot_id in self._slots:
                self._slots[slot_id]["status"] = status
                return True
            return False

    def create_appointment(
        self,
        doctor_id: str,
        slot_id: str,
        patient_name: str,
        patient_phone: str,
        patient_dob: str,
        has_insurance: bool,
        visit_reason: str,
        visit_type: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new appointment."""
        with self._lock:
            # Check idempotency
            if idempotency_key and idempotency_key in self._idempotency_cache:
                existing_id = self._idempotency_cache[idempotency_key]
                return self._appointments[existing_id]

            # Check slot availability
            slot = self._slots.get(slot_id)
            if not slot:
                raise ValueError("SLOT_NOT_FOUND")
            if slot.get("status") != "available":
                raise ValueError("SLOT_UNAVAILABLE")

            # Check doctor exists
            if doctor_id not in self._doctors:
                raise ValueError("DOCTOR_NOT_FOUND")

            # Validate visit_type
            if visit_type not in ("first_visit", "follow_up"):
                raise ValueError("INVALID_VISIT_TYPE")

            # Create appointment
            now = datetime.now(dt_timezone.utc).isoformat()
            appointment_id = self._generate_appointment_id()
            appointment = {
                "appointment_id": appointment_id,
                "doctor_id": doctor_id,
                "slot_id": slot_id,
                "patient_name": patient_name,
                "patient_phone": patient_phone,
                "patient_dob": patient_dob,
                "has_insurance": has_insurance,
                "visit_reason": visit_reason,
                "visit_type": visit_type,
                "status": self._default_status,  # Default to 'pending'
                "rejection_reason": None,
                "created_at": now,
                "updated_at": now,
            }

            self._appointments[appointment_id] = appointment

            # Update slot status
            self._slots[slot_id]["status"] = "booked"

            # Store idempotency key
            if idempotency_key:
                self._idempotency_cache[idempotency_key] = appointment_id

            return appointment

    def get_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """Get an appointment by ID."""
        with self._lock:
            return self._appointments.get(appointment_id)


# Global data store instance
_data_store: Optional[MockHISDataStore] = None


def get_data_store() -> MockHISDataStore:
    """Get or create the global data store."""
    global _data_store
    if _data_store is None:
        _data_store = MockHISDataStore()
        # Load seed data from default location
        seed_path = Path(__file__).parent.parent.parent / "data" / "mvp" / "seed" / "mock-his.json"
        _data_store.load_from_file(seed_path)
    return _data_store


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/mock-his/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "mock-his"}


@app.get("/mock-his/specialties")
async def list_specialties() -> Dict[str, Any]:
    """List all specialties.

    Returns all specialties from the seed data.
    """
    store = get_data_store()
    specialties = store.list_specialties()
    return {"specialties": specialties}


@app.get("/mock-his/doctors")
async def list_doctors() -> Dict[str, Any]:
    """List all doctors.

    Returns all doctors from the seed data.
    """
    store = get_data_store()
    doctors = store.list_doctors()
    return {"doctors": doctors}


@app.get("/mock-his/slots")
async def list_slots() -> Dict[str, Any]:
    """List all slots.

    Returns all slots from the seed data.
    """
    store = get_data_store()
    slots = store.list_slots()
    return {"slots": slots}


@app.post("/mock-his/appointments")
async def create_appointment(request: AppointmentCreateRequest) -> Dict[str, Any]:
    """Create a new appointment.

    The appointment will be created with 'pending' status by default.
    The operation is idempotent when idempotency_key is provided.

    Returns the created appointment or an error if the slot is unavailable.
    """
    store = get_data_store()

    try:
        appointment = store.create_appointment(
            doctor_id=request.doctor_id,
            slot_id=request.slot_id,
            patient_name=request.patient_name,
            patient_phone=request.patient_phone,
            patient_dob=request.patient_dob,
            has_insurance=request.has_insurance,
            visit_reason=request.visit_reason,
            visit_type=request.visit_type,
            idempotency_key=request.idempotency_key,
        )
        return appointment
    except ValueError as e:
        error_code = str(e)
        if error_code == "SLOT_UNAVAILABLE":
            return JSONResponse(
                status_code=409,
                content={"error_code": "SLOT_UNAVAILABLE", "message": "The requested slot is not available."},
            )
        elif error_code == "SLOT_NOT_FOUND":
            return JSONResponse(
                status_code=404,
                content={"error_code": "SLOT_NOT_FOUND", "message": "The specified slot does not exist."},
            )
        elif error_code == "DOCTOR_NOT_FOUND":
            return JSONResponse(
                status_code=404,
                content={"error_code": "DOCTOR_NOT_FOUND", "message": "The specified doctor does not exist."},
            )
        elif error_code == "INVALID_VISIT_TYPE":
            return JSONResponse(
                status_code=400,
                content={"error_code": "INVALID_VISIT_TYPE", "message": "Visit type must be 'first_visit' or 'follow_up'."},
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"error_code": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
            )


@app.get("/mock-his/appointments/{appointment_id}")
async def get_appointment(appointment_id: str) -> Dict[str, Any]:
    """Get an appointment by ID.

    Returns the appointment details or 404 if not found.
    """
    store = get_data_store()
    appointment = store.get_appointment(appointment_id)

    if not appointment:
        return JSONResponse(
            status_code=404,
            content={"error_code": "APPOINTMENT_NOT_FOUND", "message": f"Appointment '{appointment_id}' not found."},
        )

    return appointment


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "HTTP_ERROR", "message": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=500,
        content={"error_code": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
    )


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize data store on startup."""
    # Pre-load data to ensure it's ready when requests arrive
    get_data_store()


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "app",
    "MockHISDataStore",
    "get_data_store",
]
# === TASK:WP-104:END ===
