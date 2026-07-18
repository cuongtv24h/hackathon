# === TASK:WP-203:START ===
"""Appointment tool adapters for LLM orchestration (INT-06).

This module provides provider-neutral tool wrappers around the appointment
foundation APIs defined in WP-104. The tools follow the contracts specified
in docs/artifacts/interface/tool-contracts.md (INT-06):

- get_specialty_list: active filter → specialties
- get_doctor_list: optional specialty → doctors
- get_available_slots: doctor/date range → slots
- create_appointment: appointment + confirmation/idempotency → appointment
- lookup_appointment: appointment ID → appointment/null

Each tool wraps the corresponding foundation API operation and translates
errors to canonical tool error codes (INT-07).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from packages.contracts import (
    UnifiedErrorEnvelope,
    make_error_envelope,
    CATEGORY_TOOL,
    CATEGORY_VALIDATION,
    CATEGORY_NOT_FOUND,
    CATEGORY_BUSINESS,
    INTEGRATION_UNAVAILABLE,
    INVALID_DATE_RANGE,
    INVALID_ENUM,
    CONFIRMATION_REQUIRED,
    SLOT_UNAVAILABLE,
    INVALID_REQUEST,
)

# Import foundation service (WP-104)
from apps.api.foundation.appointments.service import (
    AppointmentService,
    AppointmentServiceError,
    MockHISClient,
    SpecialtyDTO,
    DoctorDTO,
    AvailableSlotDTO,
    AppointmentDTO,
    PatientAppointmentDataDTO,
)


# ---------------------------------------------------------------------------
# Tool-level exception
# ---------------------------------------------------------------------------


class AppointmentToolError(Exception):
    """Tool-layer exception that wraps a UnifiedErrorEnvelope (INT-07)."""

    def __init__(self, envelope: UnifiedErrorEnvelope) -> None:
        self.envelope = envelope
        super().__init__(envelope.error.message)

    def to_dict(self) -> Dict[str, Any]:
        """Return the canonical error envelope as a plain dict."""
        return self.envelope.to_dict()


def _tool_error(
    code: str,
    message: str,
    *,
    category: str = CATEGORY_TOOL,
    retryable: bool = False,
    retry_after_seconds: Optional[int] = None,
) -> AppointmentToolError:
    """Create an AppointmentToolError wrapping a UnifiedErrorEnvelope."""
    return AppointmentToolError(
        make_error_envelope(
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
        )
    )


# ---------------------------------------------------------------------------
# Tool input DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GetSpecialtyListInput:
    """Input for get_specialty_list tool."""

    active_only: bool = True


@dataclass(frozen=True)
class GetDoctorListInput:
    """Input for get_doctor_list tool."""

    specialty_id: Optional[str] = None
    active_only: bool = True


@dataclass(frozen=True)
class GetAvailableSlotsInput:
    """Input for get_available_slots tool."""

    doctor_id: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@dataclass(frozen=True)
class CreateAppointmentInput:
    """Input for create_appointment tool."""

    doctor_id: str
    slot_id: str
    patient_name: str
    patient_phone: str
    patient_dob: str
    has_insurance: bool
    visit_reason: str
    visit_type: Literal["first_visit", "follow_up"]
    confirmation_token: str
    idempotency_key: Optional[str] = None


@dataclass(frozen=True)
class LookupAppointmentInput:
    """Input for lookup_appointment tool."""

    appointment_id: str


# ---------------------------------------------------------------------------
# Tool output DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecialtyListOutput:
    """Output for get_specialty_list tool."""

    specialties: List[Dict[str, Any]]
    total: int


@dataclass(frozen=True)
class DoctorListOutput:
    """Output for get_doctor_list tool."""

    doctors: List[Dict[str, Any]]
    total: int


@dataclass(frozen=True)
class AvailableSlotsOutput:
    """Output for get_available_slots tool."""

    slots: List[Dict[str, Any]]
    total: int


@dataclass(frozen=True)
class AppointmentOutput:
    """Output for create_appointment and lookup_appointment tools."""

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


@dataclass(frozen=True)
class AppointmentNotFoundOutput:
    """Output for lookup_appointment when appointment not found."""

    appointment: None = None


# ---------------------------------------------------------------------------
# Tool adapters
# ---------------------------------------------------------------------------


class AppointmentTools:
    """Provider-neutral appointment tool adapters.

    These tools wrap the foundation appointment service and provide
    a stable interface for LLM orchestration. Each tool:
    - Validates inputs before calling the foundation service
    - Translates foundation errors to tool error codes
    - Returns structured outputs suitable for LLM consumption
    - Respects timeout/retry policies defined in INT-06
    """

    def __init__(self, appointment_service: Optional[AppointmentService] = None):
        """Initialize the tool adapters.

        Args:
            appointment_service: The foundation appointment service to use.
                If None, a default service with MockHISClient will be created.
        """
        self._service = appointment_service or AppointmentService()

    def _invoke_with_policy(self, operation, *, timeout_ms: int, retries: int = 1):
        """Apply INT-06 retry and elapsed-time policy to one HIS call."""
        last_error = None
        for attempt in range(retries + 1):
            started = time.monotonic()
            try:
                result = operation()
                if (time.monotonic() - started) * 1000 > timeout_ms:
                    raise TimeoutError(f"HIS operation exceeded {timeout_ms}ms")
                return result
            except AppointmentServiceError as exc:
                last_error = exc
                if not exc.envelope.error.retryable or attempt == retries:
                    raise
            except Exception as exc:
                last_error = exc
                if attempt == retries:
                    raise
        raise last_error or RuntimeError("HIS operation failed")

    def get_specialty_list(
        self, input_data: GetSpecialtyListInput
    ) -> SpecialtyListOutput:
        """Get list of medical specialties.

        Tool contract (INT-06):
            Input: active filter
            Output: specialties
            Errors: INTEGRATION_UNAVAILABLE
            Retry: 1
            Timeout: 500ms

        Args:
            input_data: Tool input with active_only filter.

        Returns:
            SpecialtyListOutput with list of specialties.

        Raises:
            AppointmentToolError: If the foundation service fails.
        """
        try:
            is_active = input_data.active_only if input_data.active_only else None
            page = self._invoke_with_policy(
                lambda: self._service.list_specialties(
                    page=1,
                    page_size=100,
                    is_active=is_active,
                ),
                timeout_ms=500,
            )

            specialties = [s.to_dict() for s in page.items]
            return SpecialtyListOutput(specialties=specialties, total=page.total)

        except AppointmentServiceError as e:
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to retrieve specialty list from HIS.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )
        except Exception:
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unexpected error retrieving specialty list.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def get_doctor_list(self, input_data: GetDoctorListInput) -> DoctorListOutput:
        """Get list of doctors, optionally filtered by specialty.

        Tool contract (INT-06):
            Input: optional specialty
            Output: doctors
            Errors: INVALID_SPECIALTY, INTEGRATION_UNAVAILABLE
            Retry: 1 transient
            Timeout: 700ms

        Args:
            input_data: Tool input with optional specialty_id filter.

        Returns:
            DoctorListOutput with list of doctors.

        Raises:
            AppointmentToolError: If the foundation service fails or
                invalid specialty is provided.
        """
        try:
            is_active = input_data.active_only if input_data.active_only else None
            page = self._invoke_with_policy(
                lambda: self._service.list_doctors(
                    page=1,
                    page_size=100,
                    specialty_id=input_data.specialty_id,
                    is_active=is_active,
                ),
                timeout_ms=700,
            )

            doctors = [d.to_dict() for d in page.items]
            return DoctorListOutput(doctors=doctors, total=page.total)

        except AppointmentServiceError as e:
            # Check if it's a specialty-related error
            if "specialty" in str(e).lower():
                raise _tool_error(
                    code=INVALID_ENUM,
                    message=f"Invalid specialty ID: {input_data.specialty_id}",
                    category=CATEGORY_VALIDATION,
                    retryable=False,
                )
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to retrieve doctor list from HIS.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )
        except Exception:
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unexpected error retrieving doctor list.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def get_available_slots(
        self, input_data: GetAvailableSlotsInput
    ) -> AvailableSlotsOutput:
        """Get available appointment slots for a doctor.

        Tool contract (INT-06):
            Input: doctor/date range
            Output: slots
            Errors: INVALID_DATE_RANGE, INTEGRATION_UNAVAILABLE
            Retry: 1
            Timeout: 800ms

        Args:
            input_data: Tool input with doctor_id and optional date range.

        Returns:
            AvailableSlotsOutput with list of available slots.

        Raises:
            AppointmentToolError: If date range is invalid or service fails.
        """
        # Validate date range
        if input_data.date_from and input_data.date_to:
            if input_data.date_from > input_data.date_to:
                raise _tool_error(
                    code=INVALID_DATE_RANGE,
                    message="date_from must be before or equal to date_to.",
                    category=CATEGORY_VALIDATION,
                    retryable=False,
                )

        try:
            page = self._invoke_with_policy(
                lambda: self._service.list_available_slots(
                    doctor_id=input_data.doctor_id,
                    page=1,
                    page_size=100,
                    date_from=input_data.date_from,
                    date_to=input_data.date_to,
                ),
                timeout_ms=800,
            )

            slots = [s.to_dict() for s in page.items]
            return AvailableSlotsOutput(slots=slots, total=page.total)

        except AppointmentServiceError:
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unable to retrieve available slots from HIS.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )
        except Exception:
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unexpected error retrieving available slots.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def create_appointment(
        self, input_data: CreateAppointmentInput
    ) -> AppointmentOutput:
        """Create a new appointment.

        Tool contract (INT-06):
            Input: appointment + confirmation/idempotency
            Output: appointment
            Errors: CONFIRMATION_REQUIRED, SLOT_UNAVAILABLE, DUPLICATE_REQUEST,
                    INTEGRATION_UNAVAILABLE
            Retry: 1 same key
            Timeout: 1500ms

        Args:
            input_data: Tool input with appointment details and confirmation token.

        Returns:
            AppointmentOutput with created appointment details.

        Raises:
            AppointmentToolError: If validation fails or service fails.
        """
        # Validate confirmation token
        if not input_data.confirmation_token:
            raise _tool_error(
                code=CONFIRMATION_REQUIRED,
                message="Confirmation token is required to create an appointment.",
                category=CATEGORY_BUSINESS,
                retryable=False,
            )

        # Validate visit_type
        if input_data.visit_type not in ("first_visit", "follow_up"):
            raise _tool_error(
                code=INVALID_ENUM,
                message=f"Invalid visit_type: {input_data.visit_type}. "
                "Must be 'first_visit' or 'follow_up'.",
                category=CATEGORY_VALIDATION,
                retryable=False,
            )

        try:
            patient = PatientAppointmentDataDTO(
                name=input_data.patient_name,
                phone=input_data.patient_phone,
                dob=input_data.patient_dob,
                has_insurance=input_data.has_insurance,
                visit_reason=input_data.visit_reason,
                visit_type=input_data.visit_type,
            )

            appointment = self._invoke_with_policy(
                lambda: self._service.create_appointment(
                    doctor_id=input_data.doctor_id,
                    slot_id=input_data.slot_id,
                    patient=patient,
                    confirmation_token=input_data.confirmation_token,
                    idempotency_key=input_data.idempotency_key,
                ),
                timeout_ms=1500,
            )

            return AppointmentOutput(
                appointment_id=appointment.appointment_id,
                doctor_id=appointment.doctor_id,
                slot_id=appointment.slot_id,
                patient_name=appointment.patient_name,
                patient_phone=appointment.patient_phone,
                patient_dob=appointment.patient_dob,
                has_insurance=appointment.has_insurance,
                visit_reason=appointment.visit_reason,
                visit_type=appointment.visit_type,
                status=appointment.status,
                rejection_reason=appointment.rejection_reason,
                created_at=appointment.created_at,
                updated_at=appointment.updated_at,
            )

        except AppointmentServiceError as e:
            envelope = e.envelope
            code = envelope.error.code

            # Map foundation errors to tool errors
            if code == SLOT_UNAVAILABLE:
                raise _tool_error(
                    code=SLOT_UNAVAILABLE,
                    message="The requested appointment slot is no longer available.",
                    category=CATEGORY_BUSINESS,
                    retryable=False,
                )
            elif code == CONFIRMATION_REQUIRED:
                raise _tool_error(
                    code=CONFIRMATION_REQUIRED,
                    message="Confirmation token is required to create an appointment.",
                    category=CATEGORY_BUSINESS,
                    retryable=False,
                )
            elif code == INVALID_REQUEST:
                raise _tool_error(
                    code=INVALID_REQUEST,
                    message="A similar appointment request is already being processed. "
                    "Use the idempotency key for retries.",
                    category=CATEGORY_BUSINESS,
                    retryable=False,
                )
            else:
                raise _tool_error(
                    code=INTEGRATION_UNAVAILABLE,
                    message="Unable to create appointment in HIS.",
                    category=CATEGORY_TOOL,
                    retryable=True,
                    retry_after_seconds=5,
                )
        except Exception:
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unexpected error creating appointment.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )

    def lookup_appointment(
        self, input_data: LookupAppointmentInput
    ) -> Optional[AppointmentOutput]:
        """Look up an existing appointment by ID.

        Tool contract (INT-06):
            Input: appointment ID
            Output: appointment/null
            Errors: INVALID_REFERENCE, INTEGRATION_UNAVAILABLE
            Retry: 1 transient
            Timeout: 1000ms

        Args:
            input_data: Tool input with appointment_id.

        Returns:
            AppointmentOutput if found, None if not found.

        Raises:
            AppointmentToolError: If appointment_id is invalid or service fails.
        """
        # Validate appointment_id format
        if not input_data.appointment_id:
            raise _tool_error(
                code=INVALID_REQUEST,
                message="Appointment ID is required.",
                category=CATEGORY_VALIDATION,
                retryable=False,
            )

        try:
            appointment = self._invoke_with_policy(
                lambda: self._service.get_appointment(
                    appointment_id=input_data.appointment_id
                ),
                timeout_ms=1000,
            )

            return AppointmentOutput(
                appointment_id=appointment.appointment_id,
                doctor_id=appointment.doctor_id,
                slot_id=appointment.slot_id,
                patient_name=appointment.patient_name,
                patient_phone=appointment.patient_phone,
                patient_dob=appointment.patient_dob,
                has_insurance=appointment.has_insurance,
                visit_reason=appointment.visit_reason,
                visit_type=appointment.visit_type,
                status=appointment.status,
                rejection_reason=appointment.rejection_reason,
                created_at=appointment.created_at,
                updated_at=appointment.updated_at,
            )

        except AppointmentServiceError as e:
            envelope = e.envelope
            code = envelope.error.code

            if code == "APPOINTMENT_NOT_FOUND":
                # Return None for not found (per tool contract)
                return None
            else:
                raise _tool_error(
                    code=INTEGRATION_UNAVAILABLE,
                    message="Unable to look up appointment in HIS.",
                    category=CATEGORY_TOOL,
                    retryable=True,
                    retry_after_seconds=5,
                )
        except Exception:
            raise _tool_error(
                code=INTEGRATION_UNAVAILABLE,
                message="Unexpected error looking up appointment.",
                category=CATEGORY_TOOL,
                retryable=True,
                retry_after_seconds=5,
            )


# ---------------------------------------------------------------------------
# Convenience factory function
# ---------------------------------------------------------------------------


def create_appointment_tools(
    his_base_url: str = "http://127.0.0.1:8001",
) -> AppointmentTools:
    """Create appointment tools with a configured HIS client.

    Args:
        his_base_url: Base URL for the Mock HIS service.

    Returns:
        Configured AppointmentTools instance.
    """
    his_client = MockHISClient(base_url=his_base_url)
    service = AppointmentService(his_client=his_client)
    return AppointmentTools(appointment_service=service)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "AppointmentTools",
    "AppointmentToolError",
    "GetSpecialtyListInput",
    "GetDoctorListInput",
    "GetAvailableSlotsInput",
    "CreateAppointmentInput",
    "LookupAppointmentInput",
    "SpecialtyListOutput",
    "DoctorListOutput",
    "AvailableSlotsOutput",
    "AppointmentOutput",
    "create_appointment_tools",
]
# === TASK:WP-203:END ===
