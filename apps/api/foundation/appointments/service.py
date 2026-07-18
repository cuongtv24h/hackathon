# === TASK:WP-104:START ===
"""Foundation appointment service (FND-APT-01..05).

This module implements the appointment foundation APIs declared in
``docs/artifacts/interface/foundation-api-contracts.md`` (INT-03). The five
operations are:

* ``FND-APT-01 ListSpecialties`` — ``GET /v1/foundation/specialties``
* ``FND-APT-02 ListDoctors`` — ``GET /v1/foundation/doctors``
* ``FND-APT-03 ListAvailableSlots`` — ``GET /v1/foundation/doctors/{doctor_id}/available-slots``
* ``FND-APT-04 CreateAppointment`` — ``POST /v1/foundation/appointments``
* ``FND-APT-05 GetAppointment`` — ``GET /v1/foundation/appointments/{appointment_id}``

No AI reasoning is performed; the service is pure appointment lifecycle
delegating to Mock HIS.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Literal, Mapping, Optional

from packages.contracts import (
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_NOT_FOUND,
    CATEGORY_VALIDATION,
    CATEGORY_BUSINESS,
    CATEGORY_TOOL,
    APPOINTMENT_NOT_FOUND,
    SLOT_UNAVAILABLE,
    INVALID_REQUEST,
    FIELD_REQUIRED,
    INVALID_ENUM,
    CONFIRMATION_REQUIRED,
    INTEGRATION_UNAVAILABLE,
    INTERNAL_ERROR,
)


# ---------------------------------------------------------------------------
# Service-level exception wrapping UnifiedErrorEnvelope
# ---------------------------------------------------------------------------


class AppointmentServiceError(Exception):
    """Service-layer exception that wraps a UnifiedErrorEnvelope (INT-07)."""

    def __init__(self, envelope: UnifiedErrorEnvelope) -> None:
        self.envelope = envelope
        super().__init__(envelope.error.message)

    def to_dict(self) -> Dict[str, Any]:
        """Return the canonical error envelope as a plain dict."""
        return self.envelope.to_dict()


# ---------------------------------------------------------------------------
# Internal error helper
# ---------------------------------------------------------------------------


def _service_error(
    code: str,
    message: str,
    *,
    category: str,
    field_errors: Optional[Dict[str, str]] = None,
    retryable: bool = False,
    retry_after_seconds: Optional[int] = None,
    fallback: Optional[str] = None,
) -> AppointmentServiceError:
    """Create an AppointmentServiceError wrapping a UnifiedErrorEnvelope (INT-07)."""
    return AppointmentServiceError(
        make_error_envelope(
            code=code,
            message=message,
            category=category,
            field_errors=field_errors,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            fallback=fallback,
        )
    )


# ---------------------------------------------------------------------------
# Appointment DTOs (from INT-04 / data-contracts.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecialtyDTO:
    """DTO for a medical specialty."""

    specialty_id: str
    code: str
    name: str
    department_id: str
    description: str
    is_active: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "specialty_id": self.specialty_id,
            "code": self.code,
            "name": self.name,
            "department_id": self.department_id,
            "description": self.description,
            "is_active": self.is_active,
        }


@dataclass(frozen=True)
class SpecialtyPageDTO:
    """Paginated list of specialties."""

    items: List[SpecialtyDTO]
    total: int
    page: int = 1
    page_size: int = 20

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [s.to_dict() for s in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
        }


@dataclass(frozen=True)
class DoctorDTO:
    """DTO for a doctor."""

    doctor_id: str
    full_name: str
    title: str
    specialty_ids: List[str]
    department_id: str
    facility: str
    profile_summary: str
    is_active: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doctor_id": self.doctor_id,
            "full_name": self.full_name,
            "title": self.title,
            "specialty_ids": list(self.specialty_ids),
            "department_id": self.department_id,
            "facility": self.facility,
            "profile_summary": self.profile_summary,
            "is_active": self.is_active,
        }


@dataclass(frozen=True)
class DoctorPageDTO:
    """Paginated list of doctors."""

    items: List[DoctorDTO]
    total: int
    page: int = 1
    page_size: int = 20

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [d.to_dict() for d in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
        }


@dataclass(frozen=True)
class AvailableSlotDTO:
    """DTO for an available appointment slot."""

    slot_id: str
    doctor_id: str
    date: str
    time: str
    room: str
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "doctor_id": self.doctor_id,
            "date": self.date,
            "time": self.time,
            "room": self.room,
            "status": self.status,
        }


@dataclass(frozen=True)
class AvailableSlotPageDTO:
    """Paginated list of available slots."""

    items: List[AvailableSlotDTO]
    total: int
    page: int = 1
    page_size: int = 20

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [s.to_dict() for s in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
        }


@dataclass(frozen=True)
class PatientAppointmentDataDTO:
    """Patient data for appointment creation."""

    name: str
    phone: str
    dob: str
    has_insurance: bool
    visit_reason: str
    visit_type: Literal["first_visit", "follow_up"]


@dataclass(frozen=True)
class AppointmentCreateRequest:
    """Request body for creating an appointment."""

    doctor_id: str
    slot_id: str
    patient: PatientAppointmentDataDTO
    confirmation_token: str
    idempotency_key: Optional[str] = None


@dataclass(frozen=True)
class AppointmentDTO:
    """DTO for an appointment."""

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
    rejection_reason: Optional[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appointment_id": self.appointment_id,
            "doctor_id": self.doctor_id,
            "slot_id": self.slot_id,
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "patient_dob": self.patient_dob,
            "has_insurance": self.has_insurance,
            "visit_reason": self.visit_reason,
            "visit_type": self.visit_type,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# Mock HIS client interface
# ---------------------------------------------------------------------------


class MockHISClient:
    """Client for interacting with the Mock HIS service.

    This client handles HTTP communication with the Mock HIS service
    and translates responses into domain DTOs.
    """

    def __init__(self, base_url: str = "http://localhost:8100"):
        self.base_url = base_url.rstrip("/")
        self._timeout_seconds = 5.0

    def _make_request(
        self, method: str, path: str, *, json_body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request to the Mock HIS service.

        This is a simplified implementation for testing. In production,
        this would use httpx or requests library.
        """
        # This method is designed to be mocked in tests
        raise NotImplementedError("MockHISClient._make_request must be mocked in tests")

    def list_specialties(
        self, page: int = 1, page_size: int = 20, is_active: Optional[bool] = None
    ) -> SpecialtyPageDTO:
        """List specialties from Mock HIS (FND-APT-01)."""
        try:
            params = {"page": page, "page_size": page_size}
            if is_active is not None:
                params["is_active"] = str(is_active).lower()

            response = self._make_request("GET", "/mock-his/specialties")
            specialties_data = response.get("specialties", [])

            # Filter by is_active if specified
            if is_active is not None:
                specialties_data = [
                    s for s in specialties_data if s.get("is_active") == is_active
                ]

            # Apply pagination
            start = (page - 1) * page_size
            end = start + page_size
            paginated = specialties_data[start:end]

            items = [
                SpecialtyDTO(
                    specialty_id=s["specialty_id"],
                    code=s["code"],
                    name=s["name"],
                    department_id=s["department_id"],
                    description=s.get("description", ""),
                    is_active=s.get("is_active", True),
                )
                for s in paginated
            ]

            return SpecialtyPageDTO(
                items=items, total=len(specialties_data), page=page, page_size=page_size
            )
        except Exception as e:
            if isinstance(e, AppointmentServiceError):
                raise
            raise _service_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to connect to HIS service for specialties lookup.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def list_doctors(
        self,
        page: int = 1,
        page_size: int = 20,
        specialty_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> DoctorPageDTO:
        """List doctors from Mock HIS (FND-APT-02)."""
        try:
            response = self._make_request("GET", "/mock-his/doctors")
            doctors_data = response.get("doctors", [])

            # Filter by specialty_id if specified
            if specialty_id:
                doctors_data = [
                    d for d in doctors_data if specialty_id in d.get("specialty_ids", [])
                ]

            # Filter by is_active if specified
            if is_active is not None:
                doctors_data = [
                    d for d in doctors_data if d.get("is_active") == is_active
                ]

            # Apply pagination
            start = (page - 1) * page_size
            end = start + page_size
            paginated = doctors_data[start:end]

            items = [
                DoctorDTO(
                    doctor_id=d["doctor_id"],
                    full_name=d["full_name"],
                    title=d.get("title", ""),
                    specialty_ids=d.get("specialty_ids", []),
                    department_id=d["department_id"],
                    facility=d.get("facility", ""),
                    profile_summary=d.get("profile_summary", ""),
                    is_active=d.get("is_active", True),
                )
                for d in paginated
            ]

            return DoctorPageDTO(
                items=items, total=len(doctors_data), page=page, page_size=page_size
            )
        except Exception as e:
            if isinstance(e, AppointmentServiceError):
                raise
            raise _service_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to connect to HIS service for doctors lookup.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def list_available_slots(
        self,
        doctor_id: str,
        page: int = 1,
        page_size: int = 20,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> AvailableSlotPageDTO:
        """List available slots for a doctor from Mock HIS (FND-APT-03)."""
        try:
            response = self._make_request("GET", "/mock-his/slots")
            slots_data = response.get("slots", [])

            # Filter by doctor_id
            slots_data = [s for s in slots_data if s.get("doctor_id") == doctor_id]

            # Filter by status=available
            slots_data = [s for s in slots_data if s.get("status") == "available"]

            # Filter by date range if specified
            if date_from:
                slots_data = [s for s in slots_data if s.get("date", "") >= date_from]
            if date_to:
                slots_data = [s for s in slots_data if s.get("date", "") <= date_to]

            # Sort by date, then time
            slots_data.sort(key=lambda s: (s.get("date", ""), s.get("time", "")))

            # Apply pagination
            start = (page - 1) * page_size
            end = start + page_size
            paginated = slots_data[start:end]

            items = [
                AvailableSlotDTO(
                    slot_id=s["slot_id"],
                    doctor_id=s["doctor_id"],
                    date=s["date"],
                    time=s["time"],
                    room=s["room"],
                    status=s["status"],
                )
                for s in paginated
            ]

            return AvailableSlotPageDTO(
                items=items, total=len(slots_data), page=page, page_size=page_size
            )
        except Exception as e:
            if isinstance(e, AppointmentServiceError):
                raise
            raise _service_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to connect to HIS service for slots lookup.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def create_appointment(
        self,
        doctor_id: str,
        slot_id: str,
        patient: PatientAppointmentDataDTO,
        confirmation_token: str,
        idempotency_key: Optional[str] = None,
    ) -> AppointmentDTO:
        """Create an appointment in Mock HIS (FND-APT-04)."""
        try:
            # Validate confirmation token presence
            if not confirmation_token:
                raise _service_error(
                    code=CONFIRMATION_REQUIRED,
                    message="Confirmation token is required to create an appointment.",
                    category=CATEGORY_BUSINESS,
                )

            # Build request body
            body = {
                "doctor_id": doctor_id,
                "slot_id": slot_id,
                "patient_name": patient.name,
                "patient_phone": patient.phone,
                "patient_dob": patient.dob,
                "has_insurance": patient.has_insurance,
                "visit_reason": patient.visit_reason,
                "visit_type": patient.visit_type,
                "confirmation_token": confirmation_token,
            }
            if idempotency_key:
                body["idempotency_key"] = idempotency_key

            response = self._make_request("POST", "/mock-his/appointments", json_body=body)

            # Check for slot unavailable error
            if response.get("error_code") == "SLOT_UNAVAILABLE":
                raise _service_error(
                    code=SLOT_UNAVAILABLE,
                    message="The requested appointment slot is no longer available.",
                    category=CATEGORY_BUSINESS,
                )

            apt = response
            return AppointmentDTO(
                appointment_id=apt["appointment_id"],
                doctor_id=apt["doctor_id"],
                slot_id=apt["slot_id"],
                patient_name=apt["patient_name"],
                patient_phone=apt["patient_phone"],
                patient_dob=apt["patient_dob"],
                has_insurance=apt["has_insurance"],
                visit_reason=apt["visit_reason"],
                visit_type=apt["visit_type"],
                status=apt["status"],
                rejection_reason=apt.get("rejection_reason"),
                created_at=apt["created_at"],
                updated_at=apt["updated_at"],
            )
        except Exception as e:
            if isinstance(e, AppointmentServiceError):
                raise
            raise _service_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to connect to HIS service for appointment creation.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def get_appointment(self, appointment_id: str) -> AppointmentDTO:
        """Get an appointment from Mock HIS (FND-APT-05)."""
        try:
            response = self._make_request("GET", f"/mock-his/appointments/{appointment_id}")

            if response.get("error_code") == "APPOINTMENT_NOT_FOUND" or not response.get("appointment_id"):
                raise _service_error(
                    code=APPOINTMENT_NOT_FOUND,
                    message=f"Appointment '{appointment_id}' not found.",
                    category=CATEGORY_NOT_FOUND,
                )

            apt = response
            return AppointmentDTO(
                appointment_id=apt["appointment_id"],
                doctor_id=apt["doctor_id"],
                slot_id=apt["slot_id"],
                patient_name=apt["patient_name"],
                patient_phone=apt["patient_phone"],
                patient_dob=apt["patient_dob"],
                has_insurance=apt["has_insurance"],
                visit_reason=apt["visit_reason"],
                visit_type=apt["visit_type"],
                status=apt["status"],
                rejection_reason=apt.get("rejection_reason"),
                created_at=apt["created_at"],
                updated_at=apt["updated_at"],
            )
        except Exception as e:
            if isinstance(e, AppointmentServiceError):
                raise
            raise _service_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to connect to HIS service for appointment lookup.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )


# ---------------------------------------------------------------------------
# Service class with business logic
# ---------------------------------------------------------------------------


class AppointmentService:
    """Appointment foundation service.

    This service provides the five appointment-related operations declared
    in INT-03 (Foundation API Contracts). It delegates to Mock HIS for
    data persistence and retrieval.
    """

    def __init__(self, his_client: Optional[MockHISClient] = None):
        self._his_client = his_client or MockHISClient()

    def list_specialties(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: Optional[bool] = None,
    ) -> SpecialtyPageDTO:
        """List specialties (FND-APT-01).

        Args:
            page: Page number (1-indexed).
            page_size: Number of items per page.
            is_active: Filter by active status if specified.

        Returns:
            SpecialtyPageDTO with paginated specialties.

        Raises:
            AppointmentServiceError: If HIS is unavailable.
        """
        # Validate pagination parameters
        if page < 1:
            raise _service_error(
                code=INVALID_REQUEST,
                message="Page must be >= 1.",
                category=CATEGORY_VALIDATION,
                field_errors={"page": "must be >= 1"},
            )
        if page_size < 1 or page_size > 100:
            raise _service_error(
                code=INVALID_REQUEST,
                message="Page size must be between 1 and 100.",
                category=CATEGORY_VALIDATION,
                field_errors={"page_size": "must be between 1 and 100"},
            )

        return self._his_client.list_specialties(
            page=page, page_size=page_size, is_active=is_active
        )

    def list_doctors(
        self,
        page: int = 1,
        page_size: int = 20,
        specialty_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> DoctorPageDTO:
        """List doctors (FND-APT-02).

        Args:
            page: Page number (1-indexed).
            page_size: Number of items per page.
            specialty_id: Filter by specialty if specified.
            is_active: Filter by active status if specified.

        Returns:
            DoctorPageDTO with paginated doctors.

        Raises:
            AppointmentServiceError: If HIS is unavailable.
        """
        # Validate pagination parameters
        if page < 1:
            raise _service_error(
                code=INVALID_REQUEST,
                message="Page must be >= 1.",
                category=CATEGORY_VALIDATION,
                field_errors={"page": "must be >= 1"},
            )
        if page_size < 1 or page_size > 100:
            raise _service_error(
                code=INVALID_REQUEST,
                message="Page size must be between 1 and 100.",
                category=CATEGORY_VALIDATION,
                field_errors={"page_size": "must be between 1 and 100"},
            )

        return self._his_client.list_doctors(
            page=page, page_size=page_size, specialty_id=specialty_id, is_active=is_active
        )

    def list_available_slots(
        self,
        doctor_id: str,
        page: int = 1,
        page_size: int = 20,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> AvailableSlotPageDTO:
        """List available slots for a doctor (FND-APT-03).

        Args:
            doctor_id: The doctor ID to get slots for.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            date_from: Filter slots from this date (YYYY-MM-DD).
            date_to: Filter slots to this date (YYYY-MM-DD).

        Returns:
            AvailableSlotPageDTO with paginated slots.

        Raises:
            AppointmentServiceError: If validation fails or HIS is unavailable.
        """
        # Validate doctor_id
        if not doctor_id:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="Doctor ID is required.",
                category=CATEGORY_VALIDATION,
                field_errors={"doctor_id": "is required"},
            )

        # Validate pagination parameters
        if page < 1:
            raise _service_error(
                code=INVALID_REQUEST,
                message="Page must be >= 1.",
                category=CATEGORY_VALIDATION,
                field_errors={"page": "must be >= 1"},
            )
        if page_size < 1 or page_size > 100:
            raise _service_error(
                code=INVALID_REQUEST,
                message="Page size must be between 1 and 100.",
                category=CATEGORY_VALIDATION,
                field_errors={"page_size": "must be between 1 and 100"},
            )

        # Validate date formats if provided
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if date_from and not date_pattern.match(date_from):
            raise _service_error(
                code=INVALID_REQUEST,
                message="Invalid date_from format. Use YYYY-MM-DD.",
                category=CATEGORY_VALIDATION,
                field_errors={"date_from": "must be YYYY-MM-DD format"},
            )
        if date_to and not date_pattern.match(date_to):
            raise _service_error(
                code=INVALID_REQUEST,
                message="Invalid date_to format. Use YYYY-MM-DD.",
                category=CATEGORY_VALIDATION,
                field_errors={"date_to": "must be YYYY-MM-DD format"},
            )

        return self._his_client.list_available_slots(
            doctor_id=doctor_id,
            page=page,
            page_size=page_size,
            date_from=date_from,
            date_to=date_to,
        )

    def create_appointment(
        self,
        doctor_id: str,
        slot_id: str,
        patient: PatientAppointmentDataDTO,
        confirmation_token: str,
        idempotency_key: Optional[str] = None,
    ) -> AppointmentDTO:
        """Create an appointment (FND-APT-04).

        Appointments are created with 'pending' status by default.
        The operation is idempotent when an idempotency_key is provided.

        Args:
            doctor_id: The doctor ID for the appointment.
            slot_id: The slot ID to book.
            patient: Patient information for the appointment.
            confirmation_token: Token confirming the user accepts the booking.
            idempotency_key: Optional key for idempotent requests.

        Returns:
            AppointmentDTO with the created appointment.

        Raises:
            AppointmentServiceError: If validation fails, slot is unavailable,
                or HIS is unavailable.
        """
        # Validate required fields
        if not doctor_id:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="Doctor ID is required.",
                category=CATEGORY_VALIDATION,
                field_errors={"doctor_id": "is required"},
            )
        if not slot_id:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="Slot ID is required.",
                category=CATEGORY_VALIDATION,
                field_errors={"slot_id": "is required"},
            )
        if not confirmation_token:
            raise _service_error(
                code=CONFIRMATION_REQUIRED,
                message="Confirmation token is required to create an appointment.",
                category=CATEGORY_BUSINESS,
            )

        # Validate patient data
        if not patient.name:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="Patient name is required.",
                category=CATEGORY_VALIDATION,
                field_errors={"patient.name": "is required"},
            )
        if not patient.phone:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="Patient phone is required.",
                category=CATEGORY_VALIDATION,
                field_errors={"patient.phone": "is required"},
            )
        if not patient.dob:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="Patient date of birth is required.",
                category=CATEGORY_VALIDATION,
                field_errors={"patient.dob": "is required"},
            )
        if patient.visit_type not in ("first_visit", "follow_up"):
            raise _service_error(
                code=INVALID_ENUM,
                message="Visit type must be 'first_visit' or 'follow_up'.",
                category=CATEGORY_VALIDATION,
                field_errors={"visit_type": "must be first_visit or follow_up"},
            )

        return self._his_client.create_appointment(
            doctor_id=doctor_id,
            slot_id=slot_id,
            patient=patient,
            confirmation_token=confirmation_token,
            idempotency_key=idempotency_key,
        )

    def get_appointment(self, appointment_id: str) -> AppointmentDTO:
        """Get an appointment by ID (FND-APT-05).

        Args:
            appointment_id: The appointment ID to look up.

        Returns:
            AppointmentDTO with the appointment details.

        Raises:
            AppointmentServiceError: If appointment not found or HIS unavailable.
        """
        if not appointment_id:
            raise _service_error(
                code=FIELD_REQUIRED,
                message="Appointment ID is required.",
                category=CATEGORY_VALIDATION,
                field_errors={"appointment_id": "is required"},
            )

        return self._his_client.get_appointment(appointment_id)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Exceptions
    "AppointmentServiceError",
    # DTOs
    "SpecialtyDTO",
    "SpecialtyPageDTO",
    "DoctorDTO",
    "DoctorPageDTO",
    "AvailableSlotDTO",
    "AvailableSlotPageDTO",
    "PatientAppointmentDataDTO",
    "AppointmentCreateRequest",
    "AppointmentDTO",
    # Client
    "MockHISClient",
    # Service
    "AppointmentService",
]
# === TASK:WP-104:END ===
