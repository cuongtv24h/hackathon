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
