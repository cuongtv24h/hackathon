"""Appointment tools package.

This package provides provider-neutral tool adapters for appointment operations.
"""

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
    create_appointment_tools,
)
from apps.api.foundation.appointments.tools.booking import (
    MockBookingRequest,
    book_appointment_mock,
)

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
    "MockBookingRequest",
    "book_appointment_mock",
]
