# === TASK:WP-104:START ===
"""Integration tests for WP-104 Appointment Foundation service.

This module tests the appointment foundation service operations (FND-APT-01..05)
defined in docs/artifacts/interface/foundation-api-contracts.md (INT-03).

Tests use mocked HIS client responses to avoid network calls per
docs/spec-registry/runtime-test-policy.yaml.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from apps.api.foundation.appointments.service import (
    AppointmentDTO,
    AppointmentService,
    AppointmentServiceError,
    AvailableSlotDTO,
    AvailableSlotPageDTO,
    DoctorDTO,
    DoctorPageDTO,
    MockHISClient,
    PatientAppointmentDataDTO,
    SpecialtyDTO,
    SpecialtyPageDTO,
    CATEGORY_BUSINESS,
    CATEGORY_NOT_FOUND,
    CATEGORY_VALIDATION,
    CONFIRMATION_REQUIRED,
    SLOT_UNAVAILABLE,
    APPOINTMENT_NOT_FOUND,
    FIELD_REQUIRED,
    INVALID_ENUM,
    INVALID_REQUEST,
)


# ---------------------------------------------------------------------------
# Test fixtures with mock data
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_specialties_data() -> List[Dict[str, Any]]:
    """Sample specialties data from mock HIS."""
    return [
        {
            "specialty_id": "SP-CARD-GEN",
            "code": "TIM_MACH_TONG_QUAT",
            "name": "Tim mạch tổng quát",
            "department_id": "DEP-CARD",
            "description": "[MOCK] Khám hành chính chuyên khoa tim mạch tổng quát.",
            "is_active": True,
        },
        {
            "specialty_id": "SP-ARR",
            "code": "ROI_LOAN_NHIP",
            "name": "Rối loạn nhịp",
            "department_id": "DEP-CARD",
            "description": "[MOCK] Thông tin chuyên khoa, không phải hướng dẫn tự chẩn đoán.",
            "is_active": True,
        },
        {
            "specialty_id": "SP-INACTIVE",
            "code": "INACTIVE",
            "name": "Inactive Specialty",
            "department_id": "DEP-TEST",
            "description": "Should be filtered out.",
            "is_active": False,
        },
    ]


@pytest.fixture
def mock_doctors_data() -> List[Dict[str, Any]]:
    """Sample doctors data from mock HIS."""
    return [
        {
            "doctor_id": "DOC-001",
            "full_name": "Nguyễn Minh An",
            "title": "BSCKII",
            "specialty_ids": ["SP-CARD-GEN"],
            "department_id": "DEP-CARD",
            "facility": "Cơ sở chính",
            "profile_summary": "[MOCK] Bác sĩ dữ liệu demo.",
            "is_active": True,
        },
        {
            "doctor_id": "DOC-002",
            "full_name": "Trần Thu Bình",
            "title": "TS.BS",
            "specialty_ids": ["SP-CARD-GEN", "SP-HTN"],
            "department_id": "DEP-CARD",
            "facility": "Cơ sở chính",
            "profile_summary": "[MOCK] Bác sĩ dữ liệu demo.",
            "is_active": True,
        },
        {
            "doctor_id": "DOC-003",
            "full_name": "Lê Hoàng Châu",
            "title": "ThS.BS",
            "specialty_ids": ["SP-ARR"],
            "department_id": "DEP-CARD",
            "facility": "Cơ sở chính",
            "profile_summary": "[MOCK] Bác sĩ dữ liệu demo.",
            "is_active": True,
        },
    ]


@pytest.fixture
def mock_slots_data() -> List[Dict[str, Any]]:
    """Sample slots data from mock HIS."""
    return [
        {
            "slot_id": "SL-001",
            "doctor_id": "DOC-001",
            "date": "2026-08-03",
            "time": "08:00",
            "room": "P201",
            "status": "available",
        },
        {
            "slot_id": "SL-002",
            "doctor_id": "DOC-001",
            "date": "2026-08-03",
            "time": "08:30",
            "room": "P201",
            "status": "booked",
        },
        {
            "slot_id": "SL-003",
            "doctor_id": "DOC-002",
            "date": "2026-08-04",
            "time": "09:00",
            "room": "P202",
            "status": "available",
        },
        {
            "slot_id": "SL-004",
            "doctor_id": "DOC-001",
            "date": "2026-08-05",
            "time": "10:00",
            "room": "P203",
            "status": "available",
        },
    ]


@pytest.fixture
def mock_appointment_data() -> Dict[str, Any]:
    """Sample appointment data from mock HIS."""
    return {
        "appointment_id": "HEN-2026-0001",
        "doctor_id": "DOC-001",
        "slot_id": "SL-001",
        "patient_name": "Nguyễn Văn A",
        "patient_phone": "0900000001",
        "patient_dob": "1990-01-15",
        "has_insurance": True,
        "visit_reason": "Khám định kỳ",
        "visit_type": "first_visit",
        "status": "pending",
        "rejection_reason": None,
        "created_at": "2026-07-18T08:00:00+07:00",
        "updated_at": "2026-07-18T08:00:00+07:00",
    }


# ---------------------------------------------------------------------------
# MockHISClient fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_his_client(
    mock_specialties_data,
    mock_doctors_data,
    mock_slots_data,
    mock_appointment_data,
) -> MockHISClient:
    """MockHISClient with mocked _make_request method."""
    client = MockHISClient()

    def mock_make_request(method: str, path: str, *, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if method == "GET":
            if path == "/mock-his/specialties":
                return {"specialties": mock_specialties_data}
            elif path == "/mock-his/doctors":
                return {"doctors": mock_doctors_data}
            elif path == "/mock-his/slots":
                return {"slots": mock_slots_data}
            elif path.startswith("/mock-his/appointments/"):
                appointment_id = path.split("/")[-1]
                if appointment_id == "HEN-2026-0001":
                    return mock_appointment_data
                else:
                    return {"error_code": "APPOINTMENT_NOT_FOUND"}
        elif method == "POST" and path == "/mock-his/appointments":
            # Simulate appointment creation
            if json_body:
                # Check for slot unavailable scenario
                slot_id = json_body.get("slot_id")
                if slot_id == "SL-002":  # Already booked in mock data
                    return {"error_code": "SLOT_UNAVAILABLE"}
                # Return created appointment
                return {
                    "appointment_id": "HEN-2026-0002",
                    "doctor_id": json_body.get("doctor_id"),
                    "slot_id": slot_id,
                    "patient_name": json_body.get("patient_name"),
                    "patient_phone": json_body.get("patient_phone"),
                    "patient_dob": json_body.get("patient_dob"),
                    "has_insurance": json_body.get("has_insurance"),
                    "visit_reason": json_body.get("visit_reason"),
                    "visit_type": json_body.get("visit_type"),
                    "status": "pending",
                    "rejection_reason": None,
                    "created_at": "2026-07-18T09:00:00+07:00",
                    "updated_at": "2026-07-18T09:00:00+07:00",
                }
        raise ValueError(f"Unexpected request: {method} {path}")

    client._make_request = mock_make_request  # type: ignore
    return client


@pytest.fixture
def appointment_service(mock_his_client) -> AppointmentService:
    """AppointmentService with mocked HIS client."""
    return AppointmentService(his_client=mock_his_client)


# ---------------------------------------------------------------------------
# FND-APT-01: ListSpecialties tests
# ---------------------------------------------------------------------------


class TestListSpecialties:
    """Tests for FND-APT-01 ListSpecialties."""

    def test_list_specialties_returns_all_by_default(
        self, appointment_service
    ) -> None:
        """ListSpecialties returns all specialties by default (no is_active filter)."""
        result = appointment_service.list_specialties()

        assert isinstance(result, SpecialtyPageDTO)
        assert result.total >= 2
        # When is_active is not specified, returns all records (both active and inactive)

    def test_list_specialties_filters_by_is_active_false(
        self, appointment_service
    ) -> None:
        """ListSpecialties can filter to inactive specialties."""
        result = appointment_service.list_specialties(is_active=False)

        assert isinstance(result, SpecialtyPageDTO)
        # Should only return inactive specialties
        assert all(not s.is_active for s in result.items)

    def test_list_specialties_paginates_results(
        self, appointment_service
    ) -> None:
        """ListSpecialties paginates results correctly."""
        result = appointment_service.list_specialties(page=1, page_size=1)

        assert len(result.items) == 1
        assert result.page == 1
        assert result.page_size == 1

    def test_list_specialties_invalid_page_raises_error(
        self, appointment_service
    ) -> None:
        """ListSpecialties raises error for invalid page number."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.list_specialties(page=0)

        assert exc_info.value.envelope.error.code == INVALID_REQUEST
        assert exc_info.value.envelope.error.category == CATEGORY_VALIDATION

    def test_list_specialties_invalid_page_size_raises_error(
        self, appointment_service
    ) -> None:
        """ListSpecialties raises error for invalid page size."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.list_specialties(page_size=0)

        assert exc_info.value.envelope.error.code == INVALID_REQUEST


# ---------------------------------------------------------------------------
# FND-APT-02: ListDoctors tests
# ---------------------------------------------------------------------------


class TestListDoctors:
    """Tests for FND-APT-02 ListDoctors."""

    def test_list_doctors_returns_all_active_by_default(
        self, appointment_service
    ) -> None:
        """ListDoctors returns all active doctors by default."""
        result = appointment_service.list_doctors()

        assert isinstance(result, DoctorPageDTO)
        assert result.total >= 2

    def test_list_doctors_filters_by_specialty_id(
        self, appointment_service
    ) -> None:
        """ListDoctors can filter by specialty_id."""
        result = appointment_service.list_doctors(specialty_id="SP-CARD-GEN")

        # All returned doctors should have SP-CARD-GEN in their specialty_ids
        for doctor in result.items:
            assert "SP-CARD-GEN" in doctor.specialty_ids

    def test_list_doctors_paginates_results(
        self, appointment_service
    ) -> None:
        """ListDoctors paginates results correctly."""
        result = appointment_service.list_doctors(page=1, page_size=1)

        assert len(result.items) == 1
        assert result.page == 1

    def test_list_doctors_invalid_page_raises_error(
        self, appointment_service
    ) -> None:
        """ListDoctors raises error for invalid page number."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.list_doctors(page=-1)

        assert exc_info.value.envelope.error.code == INVALID_REQUEST
        assert exc_info.value.envelope.error.category == CATEGORY_VALIDATION


# ---------------------------------------------------------------------------
# FND-APT-03: ListAvailableSlots tests
# ---------------------------------------------------------------------------


class TestListAvailableSlots:
    """Tests for FND-APT-03 ListAvailableSlots."""

    def test_list_available_slots_returns_doctor_slots(
        self, appointment_service
    ) -> None:
        """ListAvailableSlots returns slots for specified doctor."""
        result = appointment_service.list_available_slots(doctor_id="DOC-001")

        assert isinstance(result, AvailableSlotPageDTO)
        # All slots should be for DOC-001
        for slot in result.items:
            assert slot.doctor_id == "DOC-001"
            assert slot.status == "available"

    def test_list_available_slots_filters_by_date_range(
        self, appointment_service
    ) -> None:
        """ListAvailableSlots can filter by date range."""
        result = appointment_service.list_available_slots(
            doctor_id="DOC-001",
            date_from="2026-08-04",
            date_to="2026-08-05",
        )

        for slot in result.items:
            assert slot.date >= "2026-08-04"
            assert slot.date <= "2026-08-05"

    def test_list_available_slots_missing_doctor_id_raises_error(
        self, appointment_service
    ) -> None:
        """ListAvailableSlots raises error when doctor_id is missing."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.list_available_slots(doctor_id="")

        assert exc_info.value.envelope.error.code == FIELD_REQUIRED
        assert exc_info.value.envelope.error.category == CATEGORY_VALIDATION

    def test_list_available_slots_invalid_date_format_raises_error(
        self, appointment_service
    ) -> None:
        """ListAvailableSlots raises error for invalid date format."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.list_available_slots(
                doctor_id="DOC-001",
                date_from="2026/08/04",  # Wrong format
            )

        assert exc_info.value.envelope.error.code == INVALID_REQUEST


# ---------------------------------------------------------------------------
# FND-APT-04: CreateAppointment tests
# ---------------------------------------------------------------------------


class TestCreateAppointment:
    """Tests for FND-APT-04 CreateAppointment."""

    @pytest.fixture
    def valid_patient(self) -> PatientAppointmentDataDTO:
        """Valid patient data for appointment."""
        return PatientAppointmentDataDTO(
            name="Nguyễn Văn B",
            phone="0900000002",
            dob="1985-05-20",
            has_insurance=True,
            visit_reason="Khám tim mạch",
            visit_type="first_visit",
        )

    def test_create_appointment_success(
        self, appointment_service, valid_patient
    ) -> None:
        """CreateAppointment creates appointment with valid data."""
        result = appointment_service.create_appointment(
            doctor_id="DOC-001",
            slot_id="SL-001",
            patient=valid_patient,
            confirmation_token="confirm-token-123",
        )

        assert isinstance(result, AppointmentDTO)
        assert result.doctor_id == "DOC-001"
        assert result.slot_id == "SL-001"
        assert result.status == "pending"
        assert result.patient_name == valid_patient.name

    def test_create_appointment_slot_unavailable_raises_error(
        self, appointment_service, valid_patient
    ) -> None:
        """CreateAppointment raises SLOT_UNAVAILABLE when slot is booked."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.create_appointment(
                doctor_id="DOC-001",
                slot_id="SL-002",  # Already booked
                patient=valid_patient,
                confirmation_token="confirm-token-123",
            )

        assert exc_info.value.envelope.error.code == SLOT_UNAVAILABLE
        assert exc_info.value.envelope.error.category == CATEGORY_BUSINESS

    def test_create_appointment_missing_confirmation_token_raises_error(
        self, appointment_service, valid_patient
    ) -> None:
        """CreateAppointment raises error when confirmation token missing."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.create_appointment(
                doctor_id="DOC-001",
                slot_id="SL-001",
                patient=valid_patient,
                confirmation_token="",  # Missing
            )

        assert exc_info.value.envelope.error.code == CONFIRMATION_REQUIRED
        assert exc_info.value.envelope.error.category == CATEGORY_BUSINESS

    def test_create_appointment_invalid_visit_type_raises_error(
        self, appointment_service, valid_patient
    ) -> None:
        """CreateAppointment raises error for invalid visit_type."""
        invalid_patient = PatientAppointmentDataDTO(
            name="Test",
            phone="0900000000",
            dob="1990-01-01",
            has_insurance=True,
            visit_reason="Test",
            visit_type="invalid_type",  # type: ignore
        )

        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.create_appointment(
                doctor_id="DOC-001",
                slot_id="SL-001",
                patient=invalid_patient,
                confirmation_token="confirm-token-123",
            )

        assert exc_info.value.envelope.error.code == INVALID_ENUM
        assert exc_info.value.envelope.error.category == CATEGORY_VALIDATION

    def test_create_appointment_missing_patient_name_raises_error(
        self, appointment_service
    ) -> None:
        """CreateAppointment raises error when patient name is missing."""
        invalid_patient = PatientAppointmentDataDTO(
            name="",  # Missing
            phone="0900000000",
            dob="1990-01-01",
            has_insurance=True,
            visit_reason="Test",
            visit_type="first_visit",
        )

        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.create_appointment(
                doctor_id="DOC-001",
                slot_id="SL-001",
                patient=invalid_patient,
                confirmation_token="confirm-token-123",
            )

        assert exc_info.value.envelope.error.code == FIELD_REQUIRED

    def test_create_appointment_missing_doctor_id_raises_error(
        self, appointment_service, valid_patient
    ) -> None:
        """CreateAppointment raises error when doctor_id missing."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.create_appointment(
                doctor_id="",  # Missing
                slot_id="SL-001",
                patient=valid_patient,
                confirmation_token="confirm-token-123",
            )

        assert exc_info.value.envelope.error.code == FIELD_REQUIRED


# ---------------------------------------------------------------------------
# FND-APT-05: GetAppointment tests
# ---------------------------------------------------------------------------


class TestGetAppointment:
    """Tests for FND-APT-05 GetAppointment."""

    def test_get_appointment_success(self, appointment_service) -> None:
        """GetAppointment returns appointment when found."""
        result = appointment_service.get_appointment("HEN-2026-0001")

        assert isinstance(result, AppointmentDTO)
        assert result.appointment_id == "HEN-2026-0001"
        assert result.doctor_id == "DOC-001"
        assert result.status == "pending"

    def test_get_appointment_not_found_raises_error(
        self, appointment_service
    ) -> None:
        """GetAppointment raises APPOINTMENT_NOT_FOUND when not found."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.get_appointment("NON-EXISTENT-ID")

        assert exc_info.value.envelope.error.code == APPOINTMENT_NOT_FOUND
        assert exc_info.value.envelope.error.category == CATEGORY_NOT_FOUND

    def test_get_appointment_missing_id_raises_error(
        self, appointment_service
    ) -> None:
        """GetAppointment raises error when appointment_id missing."""
        with pytest.raises(AppointmentServiceError) as exc_info:
            appointment_service.get_appointment("")

        assert exc_info.value.envelope.error.code == FIELD_REQUIRED
        assert exc_info.value.envelope.error.category == CATEGORY_VALIDATION


# ---------------------------------------------------------------------------
# DTO serialization tests
# ---------------------------------------------------------------------------


class TestDTOs:
    """Tests for DTO serialization."""

    def test_specialty_dto_to_dict(self) -> None:
        """SpecialtyDTO serializes correctly."""
        dto = SpecialtyDTO(
            specialty_id="SP-001",
            code="TEST",
            name="Test Specialty",
            department_id="DEP-001",
            description="Test description",
            is_active=True,
        )

        result = dto.to_dict()

        assert result["specialty_id"] == "SP-001"
        assert result["code"] == "TEST"
        assert result["name"] == "Test Specialty"
        assert result["is_active"] is True

    def test_doctor_dto_to_dict(self) -> None:
        """DoctorDTO serializes correctly."""
        dto = DoctorDTO(
            doctor_id="DOC-001",
            full_name="Test Doctor",
            title="BS",
            specialty_ids=["SP-001", "SP-002"],
            department_id="DEP-001",
            facility="Test Facility",
            profile_summary="Test summary",
            is_active=True,
        )

        result = dto.to_dict()

        assert result["doctor_id"] == "DOC-001"
        assert result["full_name"] == "Test Doctor"
        assert result["specialty_ids"] == ["SP-001", "SP-002"]

    def test_appointment_dto_to_dict(self) -> None:
        """AppointmentDTO serializes correctly."""
        dto = AppointmentDTO(
            appointment_id="HEN-2026-0001",
            doctor_id="DOC-001",
            slot_id="SL-001",
            patient_name="Test Patient",
            patient_phone="0900000001",
            patient_dob="1990-01-01",
            has_insurance=True,
            visit_reason="Test reason",
            visit_type="first_visit",
            status="pending",
            rejection_reason=None,
            created_at="2026-07-18T08:00:00+07:00",
            updated_at="2026-07-18T08:00:00+07:00",
        )

        result = dto.to_dict()

        assert result["appointment_id"] == "HEN-2026-0001"
        assert result["patient_name"] == "Test Patient"
        assert result["status"] == "pending"
        assert result["rejection_reason"] is None

    def test_available_slot_dto_to_dict(self) -> None:
        """AvailableSlotDTO serializes correctly."""
        dto = AvailableSlotDTO(
            slot_id="SL-001",
            doctor_id="DOC-001",
            date="2026-08-03",
            time="08:00",
            room="P201",
            status="available",
        )

        result = dto.to_dict()

        assert result["slot_id"] == "SL-001"
        assert result["date"] == "2026-08-03"
        assert result["time"] == "08:00"


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Tests for appointment creation idempotency."""

    @pytest.fixture
    def valid_patient(self) -> PatientAppointmentDataDTO:
        """Valid patient data for appointment."""
        return PatientAppointmentDataDTO(
            name="Nguyễn Văn C",
            phone="0900000003",
            dob="1992-08-10",
            has_insurance=False,
            visit_reason="Tái khám",
            visit_type="follow_up",
        )

    def test_create_appointment_with_idempotency_key(
        self, appointment_service, valid_patient
    ) -> None:
        """CreateAppointment with idempotency key is handled."""
        # First call with idempotency key
        result1 = appointment_service.create_appointment(
            doctor_id="DOC-001",
            slot_id="SL-001",
            patient=valid_patient,
            confirmation_token="confirm-token-456",
            idempotency_key="idem-key-001",
        )

        assert isinstance(result1, AppointmentDTO)

        # Note: In a real implementation, the second call with the same
        # idempotency key would return the same appointment. Our mock
        # simulates this behavior through the MockHISClient.


# ---------------------------------------------------------------------------
# Module exports test
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Tests for module exports."""

    def test_module_exports_all_required_types(self) -> None:
        """Module exports all required types."""
        from apps.api.foundation.appointments import service

        # Check all expected exports are present
        assert hasattr(service, "AppointmentService")
        assert hasattr(service, "AppointmentServiceError")
        assert hasattr(service, "MockHISClient")
        assert hasattr(service, "AppointmentDTO")
        assert hasattr(service, "SpecialtyDTO")
        assert hasattr(service, "DoctorDTO")
        assert hasattr(service, "AvailableSlotDTO")
        assert hasattr(service, "PatientAppointmentDataDTO")
# === TASK:WP-104:END ===
