# === TASK:WP-203:START ===
from pydantic import BaseModel, Field
from typing import Dict, Any
from packages.contracts.dto import MockBookingReceiptDTO

class MockBookingRequest(BaseModel):
    doctor_id: str = Field(..., description="ID of the doctor")
    patient_name: str = Field(..., description="Name of the patient")
    patient_phone: str = Field(..., description="Phone number of the patient")
    schedule_date: str = Field(..., description="Date of the appointment (YYYY-MM-DD)")
    time_slot: str = Field(..., description="Time slot of the appointment (e.g. 09:00-09:30)")

def book_appointment_mock(request: MockBookingRequest) -> Dict[str, Any]:
    """Mock booking tool that creates a safe, pending mock appointment receipt without side-effects."""
    # Strict validation: prevent real-looking confirmed status
    receipt = MockBookingReceiptDTO(
        appointment_id="MOCK-APT-99999",
        status="mock_pending",
        detail="Lịch hẹn đang ở trạng thái chờ xử lý thử nghiệm. Đây là hệ thống demo, không có lịch hẹn thực tế nào được đặt."
    )
    return {
        "outcome": "success",
        "message": "Yêu cầu đặt lịch hẹn của bạn đã được ghi nhận ở chế độ thử nghiệm.",
        "appointment": receipt.to_dict()
    }
# === TASK:WP-203:END ===
