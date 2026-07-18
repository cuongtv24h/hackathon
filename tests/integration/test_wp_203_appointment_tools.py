# === TASK:WP-203:START ===
"""Integration tests for WP-203 Appointment Tools.

These tests verify the appointment tool adapters defined in:
- docs/artifacts/interface/tool-contracts.md (INT-06)
- apps/api/foundation/appointments/tools/service.py

The tests use mocks/fakes for the Mock HIS provider as required by
docs/spec-registry/runtime-test-policy.yaml.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from apps.api.foundation.appointments.tools.service import (
    AppointmentTools,
    AppointmentToolError,
    GetSpecialtyListInput,
    GetDoctorListInput,
    GetAvailableSlotsInput,
    CreateAppointmentInput,
    LookupAppointmentInput,
    SpecialtyListOutput,
    DoctorListOutput,
    AvailableSlotsOutput,
    AppointmentOutput,
)
from apps.api.foundation.appointments.service import (
    AppointmentService,
    AppointmentServiceError,
    SpecialtyDTO,
    SpecialtyPageDTO,
    DoctorDTO,
    DoctorPageDTO,
    AvailableSlotDTO,
    AvailableSlotPageDTO,
    AppointmentDTO,
)
from packages.contracts import (
    INTEGRATION_UNAVAILABLE,
    INVALID_DATE_RANGE,
    INVALID_ENUM,
    INVALID_REQUEST,
    CONFIRMATION_REQUIRED,
    SLOT_UNAVAILABLE,
    CATEGORY_TOOL,
    CATEGORY_VALIDATION,
    CATEGORY_BUSINESS,
)


# ---------------------------------------------------------------------------
# Fake MockHISClient for testing
# ---------------------------------------------------------------------------


class FakeMockHISClient:
    """Fake HIS client with controllable behavior for testing."""

    def __init__(self):
        self._specialties: List[Dict[str, Any]] = [
            {
                "specialty_id": "SP-001",
                "code": "CARDIO",
                "name": "Cardiology",
                "department_id": "DPT-001",
                "description": "Heart and cardiovascular system",
                "is_active": True,
            },
            {
                "specialty_id": "SP-002",
                "code": "NEURO",
                "name": "Neurology",
                "department_id": "DPT-002",
                "description": "Brain and nervous system",
                "is_active": True,
            },
            {
                "specialty_id": "SP-003",
                "code": "ORTHO",
                "name": "Orthopedics",
                "department_id": "DPT-003",
                "description": "Bones and joints",
                "is_active": False,
            },
        ]
        self._doctors: List[Dict[str, Any]] = [
            {
                "doctor_id": "DR-001",
                "full_name": "Dr. Nguyen Van A",
                "title": "MD, PhD",
                "specialty_ids": ["SP-001"],
                "department_id": "DPT-001",
                "facility": "Hanoi Heart Hospital",
                "profile_summary": "Expert in interventional cardiology",
                "is_active": True,
            },
            {
                "doctor_id": "DR-002",
                "full_name": "Dr. Tran Van B",
                "title": "MD",
                "specialty_ids": ["SP-001", "SP-002"],
                "department_id": "DPT-001",
                "facility": "Hanoi Heart Hospital",
                "profile_summary": "General cardiologist",
                "is_active": True,
            },
        ]
        self._slots: List[Dict[str, Any]] = [
            {
                "slot_id": "SLOT-001",
                "doctor_id": "DR-001",
                "date": "2024-01-15",
                "time": "08:00",
                "room": "Room 101",
                "status": "available",
            },
            {
                "slot_id": "SLOT-002",
                "doctor_id": "DR-001",
                "date": "2024-01-15",
                "time": "09:00",
                "room": "Room 101",
                "status": "available",
            },
            {
                "slot_id": "SLOT-003",
                "doctor_id": "DR-001",
                "date": "2024-01-16",
                "time": "10:00",
                "room": "Room 102",
                "status": "available",
            },
            {
                "slot_id": "SLOT-004",
                "doctor_id": "DR-002",
                "date": "2024-01-15",
                "time": "14:00",
                "room": "Room 201",
                "status": "available",
            },
        ]
        self._appointments: Dict[str, Dict[str, Any]] = {
            "HEN-2024-0001": {
                "appointment_id": "HEN-2024-0001",
                "doctor_id": "DR-001",
                "slot_id": "SLOT-001",
                "patient_name": "Test Patient",
                "patient_phone": "0901234567",
                "patient_dob": "1990-01-01",
                "has_insurance": True,
                "visit_reason": "Chest pain",
                "visit_type": "first_visit",
                "status": "pending",
                "rejection_reason": None,
                "created_at": "2024-01-10T10:00:00Z",
                "updated_at": "2024-01-10T10:00:00Z",
            }
        }
        self._raise_error: Optional[str] = None
        self._appointment_counter = 1

    def set_raise_error(self, error_type: Optional[str]) -> None:
        """Configure the client to raise an error on next call."""
        self._raise_error = error_type

    def list_specialties(
        self, page: int = 1, page_size: int = 20, is_active: Optional[bool] = None
    ) -> SpecialtyPageDTO:
        """Return fake specialties."""
        if self._raise_error:
            raise Exception("Connection failed")

        data = self._specialties
        if is_active is not None:
            data = [s for s in data if s.get("is_active") == is_active]

        start = (page - 1) * page_size
        end = start + page_size
        items = [
            SpecialtyDTO(
                specialty_id=s["specialty_id"],
                code=s["code"],
                name=s["name"],
                department_id=s["department_id"],
                description=s.get("description", ""),
                is_active=s.get("is_active", True),
            )
            for s in data[start:end]
        ]
        return SpecialtyPageDTO(items=items, total=len(data), page=page, page_size=page_size)

    def list_doctors(
        self,
        page: int = 1,
        page_size: int = 20,
        specialty_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> DoctorPageDTO:
        """Return fake doctors."""
        if self._raise_error:
            raise Exception("Connection failed")

        data = self._doctors
        if specialty_id:
            data = [d for d in data if specialty_id in d.get("specialty_ids", [])]
        if is_active is not None:
            data = [d for d in data if d.get("is_active") == is_active]

        start = (page - 1) * page_size
        end = start + page_size
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
            for d in data[start:end]
        ]
        return DoctorPageDTO(items=items, total=len(data), page=page, page_size=page_size)

    def list_available_slots(
        self,
        doctor_id: str,
        page: int = 1,
        page_size: int = 20,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> AvailableSlotPageDTO:
        """Return fake available slots."""
        if self._raise_error:
            raise Exception("Connection failed")

        data = [s for s in self._slots if s.get("doctor_id") == doctor_id]
        data = [s for s in data if s.get("status") == "available"]

        if date_from:
            data = [s for s in data if s.get("date", "") >= date_from]
        if date_to:
            data = [s for s in data if s.get("date", "") <= date_to]

        data.sort(key=lambda s: (s.get("date", ""), s.get("time", "")))

        start = (page - 1) * page_size
        end = start + page_size
        items = [
            AvailableSlotDTO(
                slot_id=s["slot_id"],
                doctor_id=s["doctor_id"],
                date=s["date"],
                time=s["time"],
                room=s["room"],
                status=s["status"],
            )
            for s in data[start:end]
        ]
        return AvailableSlotPageDTO(items=items, total=len(data), page=page, page_size=page_size)

    def create_appointment(
        self,
        doctor_id: str,
        slot_id: str,
        patient,
        confirmation_token: str,
        idempotency_key: Optional[str] = None,
    ) -> AppointmentDTO:
        """Create a fake appointment."""
        if self._raise_error:
            raise Exception("Connection failed")

        if not confirmation_token:
            from apps.api.foundation.appointments.service import _service_error
            from packages.contracts import CONFIRMATION_REQUIRED, CATEGORY_BUSINESS
            raise _service_error(
                code=CONFIRMATION_REQUIRED,
                message="Confirmation token required",
                category=CATEGORY_BUSINESS,
            )

        # Check if slot is available
        slot = next((s for s in self._slots if s["slot_id"] == slot_id), None)
        if not slot or slot.get("status") != "available":
            from apps.api.foundation.appointments.service import _service_error
            from packages.contracts import SLOT_UNAVAILABLE, CATEGORY_BUSINESS
            raise _service_error(
                code=SLOT_UNAVAILABLE,
                message="Slot not available",
                category=CATEGORY_BUSINESS,
            )

        self._appointment_counter += 1
        appointment_id = f"HEN-2024-{self._appointment_counter:04d}"

        appointment = {
            "appointment_id": appointment_id,
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "patient_name": patient.name,
            "patient_phone": patient.phone,
            "patient_dob": patient.dob,
            "has_insurance": patient.has_insurance,
            "visit_reason": patient.visit_reason,
            "visit_type": patient.visit_type,
            "status": "pending",
            "rejection_reason": None,
            "created_at": "2024-01-10T11:00:00Z",
            "updated_at": "2024-01-10T11:00:00Z",
        }
        self._appointments[appointment_id] = appointment

        return AppointmentDTO(
            appointment_id=appointment["appointment_id"],
            doctor_id=appointment["doctor_id"],
            slot_id=appointment["slot_id"],
            patient_name=appointment["patient_name"],
            patient_phone=appointment["patient_phone"],
            patient_dob=appointment["patient_dob"],
            has_insurance=appointment["has_insurance"],
            visit_reason=appointment["visit_reason"],
            visit_type=appointment["visit_type"],
            status=appointment["status"],
            rejection_reason=appointment["rejection_reason"],
            created_at=appointment["created_at"],
            updated_at=appointment["updated_at"],
        )

    def get_appointment(self, appointment_id: str) -> AppointmentDTO:
        """Get a fake appointment."""
        if self._raise_error:
            raise Exception("Connection failed")

        apt = self._appointments.get(appointment_id)
        if not apt:
            from apps.api.foundation.appointments.service import _service_error
            from packages.contracts import APPOINTMENT_NOT_FOUND, CATEGORY_NOT_FOUND
            raise _service_error(
                code=APPOINTMENT_NOT_FOUND,
                message=f"Appointment '{appointment_id}' not found",
                category=CATEGORY_NOT_FOUND,
            )

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
            rejection_reason=apt["rejection_reason"],
            created_at=apt["created_at"],
            updated_at=apt["updated_at"],
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_his_client() -> FakeMockHISClient:
    """Provide a fake HIS client for testing."""
    return FakeMockHISClient()


@pytest.fixture
def appointment_service(fake_his_client: FakeMockHISClient) -> AppointmentService:
    """Provide an appointment service with fake HIS client."""
    return AppointmentService(his_client=fake_his_client)


@pytest.fixture
def appointment_tools(appointment_service: AppointmentService) -> AppointmentTools:
    """Provide appointment tools with fake service."""
    return AppointmentTools(appointment_service=appointment_service)


# ---------------------------------------------------------------------------
# Test get_specialty_list tool
# ---------------------------------------------------------------------------


class TestGetSpecialtyList:
    """Tests for get_specialty_list tool."""

    def test_returns_active_specialties(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that active specialties are returned."""
        input_data = GetSpecialtyListInput(active_only=True)
        result = appointment_tools.get_specialty_list(input_data)

        assert isinstance(result, SpecialtyListOutput)
        assert result.total == 2  # Only active specialties
        assert len(result.specialties) == 2
        assert all(s["is_active"] for s in result.specialties)

    def test_returns_all_specialties(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that all specialties are returned when active_only is False."""
        input_data = GetSpecialtyListInput(active_only=False)
        result = appointment_tools.get_specialty_list(input_data)

        assert result.total == 3  # All specialties including inactive

    def test_returns_specialty_fields(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that specialty output contains required fields."""
        input_data = GetSpecialtyListInput(active_only=True)
        result = appointment_tools.get_specialty_list(input_data)

        specialty = result.specialties[0]
        assert "specialty_id" in specialty
        assert "code" in specialty
        assert "name" in specialty
        assert "department_id" in specialty
        assert "is_active" in specialty

    def test_handles_integration_error(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that integration errors are properly wrapped."""
        fake_his_client.set_raise_error("connection")
        input_data = GetSpecialtyListInput(active_only=True)

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.get_specialty_list(input_data)

        assert exc_info.value.envelope.error.code == INTEGRATION_UNAVAILABLE
        assert exc_info.value.envelope.error.retryable is True


# ---------------------------------------------------------------------------
# Test get_doctor_list tool
# ---------------------------------------------------------------------------


class TestGetDoctorList:
    """Tests for get_doctor_list tool."""

    def test_returns_all_doctors(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that all doctors are returned."""
        input_data = GetDoctorListInput()
        result = appointment_tools.get_doctor_list(input_data)

        assert isinstance(result, DoctorListOutput)
        assert result.total == 2
        assert len(result.doctors) == 2

    def test_filters_by_specialty(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that doctors are filtered by specialty."""
        input_data = GetDoctorListInput(specialty_id="SP-001")
        result = appointment_tools.get_doctor_list(input_data)

        # Both DR-001 and DR-002 have SP-001
        assert result.total == 2

    def test_returns_doctor_fields(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that doctor output contains required fields."""
        input_data = GetDoctorListInput()
        result = appointment_tools.get_doctor_list(input_data)

        doctor = result.doctors[0]
        assert "doctor_id" in doctor
        assert "full_name" in doctor
        assert "specialty_ids" in doctor
        assert "is_active" in doctor

    def test_handles_integration_error(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that integration errors are properly wrapped."""
        fake_his_client.set_raise_error("connection")
        input_data = GetDoctorListInput()

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.get_doctor_list(input_data)

        assert exc_info.value.envelope.error.code == INTEGRATION_UNAVAILABLE


# ---------------------------------------------------------------------------
# Test get_available_slots tool
# ---------------------------------------------------------------------------


class TestGetAvailableSlots:
    """Tests for get_available_slots tool."""

    def test_returns_slots_for_doctor(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that slots are returned for a specific doctor."""
        input_data = GetAvailableSlotsInput(doctor_id="DR-001")
        result = appointment_tools.get_available_slots(input_data)

        assert isinstance(result, AvailableSlotsOutput)
        assert result.total == 3  # DR-001 has 3 available slots
        assert all(s["doctor_id"] == "DR-001" for s in result.slots)

    def test_filters_by_date_range(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that slots are filtered by date range."""
        input_data = GetAvailableSlotsInput(
            doctor_id="DR-001",
            date_from="2024-01-15",
            date_to="2024-01-15",
        )
        result = appointment_tools.get_available_slots(input_data)

        # Only slots on 2024-01-15 for DR-001
        assert result.total == 2
        assert all(s["date"] == "2024-01-15" for s in result.slots)

    def test_returns_slot_fields(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that slot output contains required fields."""
        input_data = GetAvailableSlotsInput(doctor_id="DR-001")
        result = appointment_tools.get_available_slots(input_data)

        slot = result.slots[0]
        assert "slot_id" in slot
        assert "doctor_id" in slot
        assert "date" in slot
        assert "time" in slot
        assert "room" in slot
        assert "status" in slot

    def test_rejects_invalid_date_range(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that invalid date range raises error."""
        input_data = GetAvailableSlotsInput(
            doctor_id="DR-001",
            date_from="2024-01-20",
            date_to="2024-01-10",  # date_from > date_to
        )

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.get_available_slots(input_data)

        assert exc_info.value.envelope.error.code == INVALID_DATE_RANGE
        assert exc_info.value.envelope.error.category == CATEGORY_VALIDATION

    def test_handles_integration_error(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that integration errors are properly wrapped."""
        fake_his_client.set_raise_error("connection")
        input_data = GetAvailableSlotsInput(doctor_id="DR-001")

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.get_available_slots(input_data)

        assert exc_info.value.envelope.error.code == INTEGRATION_UNAVAILABLE


# ---------------------------------------------------------------------------
# Test create_appointment tool
# ---------------------------------------------------------------------------


class TestCreateAppointment:
    """Tests for create_appointment tool."""

    def test_creates_appointment(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test successful appointment creation."""
        input_data = CreateAppointmentInput(
            doctor_id="DR-001",
            slot_id="SLOT-002",
            patient_name="Nguyen Van Test",
            patient_phone="0912345678",
            patient_dob="1985-05-15",
            has_insurance=True,
            visit_reason="Regular checkup",
            visit_type="first_visit",
            confirmation_token="confirm-token-123",
        )
        result = appointment_tools.create_appointment(input_data)

        assert isinstance(result, AppointmentOutput)
        assert result.doctor_id == "DR-001"
        assert result.slot_id == "SLOT-002"
        assert result.patient_name == "Nguyen Van Test"
        assert result.status == "pending"

    def test_requires_confirmation_token(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that confirmation token is required."""
        input_data = CreateAppointmentInput(
            doctor_id="DR-001",
            slot_id="SLOT-002",
            patient_name="Test Patient",
            patient_phone="0912345678",
            patient_dob="1985-05-15",
            has_insurance=True,
            visit_reason="Checkup",
            visit_type="first_visit",
            confirmation_token="",  # Empty token
        )

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.create_appointment(input_data)

        assert exc_info.value.envelope.error.code == CONFIRMATION_REQUIRED

    def test_validates_visit_type(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that visit_type is validated."""
        # Note: Python typing prevents invalid visit_type at compile time,
        # but we can test the validation logic directly
        input_data = CreateAppointmentInput(
            doctor_id="DR-001",
            slot_id="SLOT-002",
            patient_name="Test Patient",
            patient_phone="0912345678",
            patient_dob="1985-05-15",
            has_insurance=True,
            visit_reason="Checkup",
            visit_type="invalid_type",  # type: ignore
            confirmation_token="token",
        )

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.create_appointment(input_data)

        assert exc_info.value.envelope.error.code == INVALID_ENUM

    def test_handles_slot_unavailable(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that slot unavailable error is handled."""
        # Mark slot as booked
        for slot in fake_his_client._slots:
            if slot["slot_id"] == "SLOT-002":
                slot["status"] = "booked"

        input_data = CreateAppointmentInput(
            doctor_id="DR-001",
            slot_id="SLOT-002",
            patient_name="Test Patient",
            patient_phone="0912345678",
            patient_dob="1985-05-15",
            has_insurance=True,
            visit_reason="Checkup",
            visit_type="first_visit",
            confirmation_token="token",
        )

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.create_appointment(input_data)

        assert exc_info.value.envelope.error.code == SLOT_UNAVAILABLE
        assert exc_info.value.envelope.error.category == CATEGORY_BUSINESS

    def test_returns_appointment_fields(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that appointment output contains required fields."""
        input_data = CreateAppointmentInput(
            doctor_id="DR-001",
            slot_id="SLOT-002",
            patient_name="Test Patient",
            patient_phone="0912345678",
            patient_dob="1985-05-15",
            has_insurance=True,
            visit_reason="Checkup",
            visit_type="first_visit",
            confirmation_token="token",
        )
        result = appointment_tools.create_appointment(input_data)

        # Check all required fields
        assert result.appointment_id is not None
        assert result.doctor_id == "DR-001"
        assert result.slot_id == "SLOT-002"
        assert result.patient_name == "Test Patient"
        assert result.patient_phone == "0912345678"
        assert result.patient_dob == "1985-05-15"
        assert result.has_insurance is True
        assert result.visit_reason == "Checkup"
        assert result.visit_type == "first_visit"
        assert result.status == "pending"

    def test_handles_integration_error(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that integration errors are properly wrapped."""
        fake_his_client.set_raise_error("connection")
        input_data = CreateAppointmentInput(
            doctor_id="DR-001",
            slot_id="SLOT-002",
            patient_name="Test Patient",
            patient_phone="0912345678",
            patient_dob="1985-05-15",
            has_insurance=True,
            visit_reason="Checkup",
            visit_type="first_visit",
            confirmation_token="token",
        )

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.create_appointment(input_data)

        assert exc_info.value.envelope.error.code == INTEGRATION_UNAVAILABLE


# ---------------------------------------------------------------------------
# Test lookup_appointment tool
# ---------------------------------------------------------------------------


class TestLookupAppointment:
    """Tests for lookup_appointment tool."""

    def test_returns_existing_appointment(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that existing appointment is returned."""
        input_data = LookupAppointmentInput(appointment_id="HEN-2024-0001")
        result = appointment_tools.lookup_appointment(input_data)

        assert result is not None
        assert isinstance(result, AppointmentOutput)
        assert result.appointment_id == "HEN-2024-0001"
        assert result.doctor_id == "DR-001"

    def test_returns_none_for_not_found(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that None is returned for non-existent appointment."""
        input_data = LookupAppointmentInput(appointment_id="HEN-2024-9999")
        result = appointment_tools.lookup_appointment(input_data)

        assert result is None

    def test_requires_appointment_id(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that appointment_id is required."""
        input_data = LookupAppointmentInput(appointment_id="")

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.lookup_appointment(input_data)

        assert exc_info.value.envelope.error.code == INVALID_REQUEST

    def test_returns_appointment_fields(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Test that appointment output contains required fields."""
        input_data = LookupAppointmentInput(appointment_id="HEN-2024-0001")
        result = appointment_tools.lookup_appointment(input_data)

        assert result is not None
        assert result.appointment_id == "HEN-2024-0001"
        assert result.doctor_id == "DR-001"
        assert result.slot_id == "SLOT-001"
        assert result.patient_name == "Test Patient"
        assert result.status == "pending"

    def test_handles_integration_error(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that integration errors are properly wrapped."""
        fake_his_client.set_raise_error("connection")
        input_data = LookupAppointmentInput(appointment_id="HEN-2024-0001")

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.lookup_appointment(input_data)

        assert exc_info.value.envelope.error.code == INTEGRATION_UNAVAILABLE


# ---------------------------------------------------------------------------
# Test tool contract shape
# ---------------------------------------------------------------------------


class TestToolContractShape:
    """Tests verifying tool contracts match INT-06 specification."""

    def test_specialty_list_contract_shape(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Verify get_specialty_list output matches contract."""
        input_data = GetSpecialtyListInput(active_only=True)
        result = appointment_tools.get_specialty_list(input_data)

        # Contract: active filter → specialties
        assert hasattr(result, "specialties")
        assert hasattr(result, "total")
        assert isinstance(result.specialties, list)

    def test_doctor_list_contract_shape(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Verify get_doctor_list output matches contract."""
        input_data = GetDoctorListInput(specialty_id="SP-001")
        result = appointment_tools.get_doctor_list(input_data)

        # Contract: optional specialty → doctors
        assert hasattr(result, "doctors")
        assert hasattr(result, "total")
        assert isinstance(result.doctors, list)

    def test_available_slots_contract_shape(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Verify get_available_slots output matches contract."""
        input_data = GetAvailableSlotsInput(
            doctor_id="DR-001",
            date_from="2024-01-15",
            date_to="2024-01-16",
        )
        result = appointment_tools.get_available_slots(input_data)

        # Contract: doctor/date range → slots
        assert hasattr(result, "slots")
        assert hasattr(result, "total")
        assert isinstance(result.slots, list)

    def test_create_appointment_contract_shape(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Verify create_appointment output matches contract."""
        input_data = CreateAppointmentInput(
            doctor_id="DR-001",
            slot_id="SLOT-002",
            patient_name="Contract Test",
            patient_phone="0901234567",
            patient_dob="1990-01-01",
            has_insurance=False,
            visit_reason="Test",
            visit_type="follow_up",
            confirmation_token="test-token",
            idempotency_key="test-key-123",
        )
        result = appointment_tools.create_appointment(input_data)

        # Contract: appointment + confirmation/idempotency → appointment
        assert hasattr(result, "appointment_id")
        assert hasattr(result, "doctor_id")
        assert hasattr(result, "slot_id")
        assert hasattr(result, "status")
        assert hasattr(result, "created_at")

    def test_lookup_appointment_contract_shape(
        self, appointment_tools: AppointmentTools
    ) -> None:
        """Verify lookup_appointment output matches contract."""
        # Test with existing appointment
        input_data = LookupAppointmentInput(appointment_id="HEN-2024-0001")
        result = appointment_tools.lookup_appointment(input_data)

        # Contract: appointment ID → appointment/null
        # When found, should have appointment fields
        if result is not None:
            assert hasattr(result, "appointment_id")
            assert hasattr(result, "status")

        # Test with non-existing appointment
        input_data = LookupAppointmentInput(appointment_id="HEN-2024-9999")
        result = appointment_tools.lookup_appointment(input_data)

        # When not found, should be None
        assert result is None


# ---------------------------------------------------------------------------
# Test error contract compliance
# ---------------------------------------------------------------------------


class TestErrorContractCompliance:
    """Tests verifying error envelopes comply with INT-07."""

    def test_tool_error_has_required_fields(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that tool errors contain all required envelope fields."""
        fake_his_client.set_raise_error("connection")
        input_data = GetSpecialtyListInput(active_only=True)

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.get_specialty_list(input_data)

        envelope = exc_info.value.envelope
        # INT-07 envelope structure
        assert hasattr(envelope, "trace_id")
        assert hasattr(envelope, "error")
        assert hasattr(envelope.error, "code")
        assert hasattr(envelope.error, "message")
        assert hasattr(envelope.error, "category")
        assert hasattr(envelope.error, "retryable")

    def test_tool_error_to_dict_returns_valid_dict(
        self, fake_his_client: FakeMockHISClient, appointment_tools: AppointmentTools
    ) -> None:
        """Test that to_dict returns a valid dictionary."""
        fake_his_client.set_raise_error("connection")
        input_data = GetSpecialtyListInput(active_only=True)

        with pytest.raises(AppointmentToolError) as exc_info:
            appointment_tools.get_specialty_list(input_data)

        error_dict = exc_info.value.to_dict()
        assert isinstance(error_dict, dict)
        assert "trace_id" in error_dict
        assert "error" in error_dict


class TestExecutionPolicy:
    """Verify INT-06 retry and timeout enforcement around HIS operations."""

    def test_retries_transient_operation_once(self) -> None:
        tool = AppointmentTools()
        attempts = {"count": 0}

        def flaky_operation():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary HIS error")
            return "ok"

        assert tool._invoke_with_policy(flaky_operation, timeout_ms=100) == "ok"
        assert attempts["count"] == 2

    def test_rejects_late_his_result(self) -> None:
        tool = AppointmentTools()
        with pytest.raises(TimeoutError, match="exceeded"):
            tool._invoke_with_policy(
                lambda: (time.sleep(0.001), "late")[1],
                timeout_ms=0,
                retries=0,
            )


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "FakeMockHISClient",
    "TestGetSpecialtyList",
    "TestGetDoctorList",
    "TestGetAvailableSlots",
    "TestCreateAppointment",
    "TestLookupAppointment",
    "TestToolContractShape",
    "TestErrorContractCompliance",
    "TestExecutionPolicy",
]
# === TASK:WP-203:END ===
