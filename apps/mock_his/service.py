"""In-memory Mock HIS implementation for the MVP pilot.

It loads only the approved mock dataset in ``data/mvp/seed/mock-his.json``.
This service is deliberately separate from the Hospital API so integration
code uses the same HTTP boundary that a future HIS adapter will use.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock


class MockHISStore:
    """Stateful, process-local representation of the Mock HIS seed data."""

    def __init__(self, seed_path=None):
        path = Path(seed_path) if seed_path else self._default_seed_path()
        with path.open("r", encoding="utf-8") as seed_file:
            payload = json.load(seed_file)
        self._dataset = payload["dataset"]
        self._specialties = payload["specialties"]
        self._doctors = payload["doctors"]
        self._slots = payload["slots"]
        self._appointments = {
            item["appointment_id"]: item for item in payload.get("appointments", [])
        }
        self._idempotency_keys = {}
        self._lock = Lock()

    @staticmethod
    def _default_seed_path():
        return Path(__file__).resolve().parents[2] / "data" / "mvp" / "seed" / "mock-his.json"

    def specialties(self):
        return deepcopy(self._specialties)

    def doctors(self):
        return deepcopy(self._doctors)

    def slots(self):
        return deepcopy(self._slots)

    def appointment(self, appointment_id):
        item = self._appointments.get(appointment_id)
        return deepcopy(item) if item else None

    def create_appointment(self, request):
        """Create a pending appointment exactly once for an idempotency key."""
        key = request.get("idempotency_key")
        if not key:
            return None, "IDEMPOTENCY_KEY_REQUIRED"

        with self._lock:
            existing_id = self._idempotency_keys.get(key)
            if existing_id:
                return deepcopy(self._appointments[existing_id]), None

            doctor_id = request.get("doctor_id")
            slot_id = request.get("slot_id")
            slot = next((item for item in self._slots if item["slot_id"] == slot_id), None)
            if not slot or slot["doctor_id"] != doctor_id or slot["status"] != "available":
                return None, "SLOT_UNAVAILABLE"

            next_number = max(
                (int(item.rsplit("-", 1)[-1]) for item in self._appointments), default=0
            ) + 1
            appointment_id = f"HEN-2026-{next_number:04d}"
            now = datetime.now(timezone.utc).isoformat()
            appointment = {
                "appointment_id": appointment_id,
                "doctor_id": doctor_id,
                "slot_id": slot_id,
                "patient_name": request["patient_name"],
                "patient_phone": request["patient_phone"],
                "patient_dob": request["patient_dob"],
                "has_insurance": request["has_insurance"],
                "visit_reason": request["visit_reason"],
                "visit_type": request["visit_type"],
                "status": self._dataset["default_appointment_status"],
                "rejection_reason": None,
                "created_at": now,
                "updated_at": now,
            }
            slot["status"] = "booked"
            self._appointments[appointment_id] = appointment
            self._idempotency_keys[key] = appointment_id
            return deepcopy(appointment), None
